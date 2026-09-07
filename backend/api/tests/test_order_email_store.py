"""
Переезд журнала заказов из писем в базу.

Журнал читают и пишут три процесса: робот почты, робот заведения заказов
и страница «Заказы сайта». Файл они переписывали целиком — 21.07.2026 так
пропал заказ 532598916.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api.models import OrderEmailMessage, OrderEmailOrder, OrderEmailState

_HORSEBIO = os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio')
sys.path.insert(0, os.path.join(_HORSEBIO, '_shared'))

from order_email_store import load_state, save_state, state_lock, last_checked_at  # noqa: E402
from order_email_store import forget_order  # noqa: E402

ORDER = {'latest': {'status': 'Оплачен', 'paid': True},
         'history': [{'message_id': '<a@site.m>'}],
         'ms': {'id': 'ms-1'}}
STATE = {'processed_message_ids': ['<a@site.m>', '<b@site.m>'],
         'orders': {'535513316': ORDER},
         'last_checked_date': '2026-09-07'}


def _state_file(data=None):
    tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
    json.dump(STATE if data is None else data, tmp, ensure_ascii=False)
    tmp.close()
    return Path(tmp.name)


class ImportOrderEmailsTests(TestCase):
    def test_import_moves_orders_messages_and_date(self):
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_order_emails', '--path', str(path))

        self.assertEqual(OrderEmailOrder.objects.get(order_id='535513316').payload, ORDER)
        self.assertEqual(OrderEmailMessage.objects.count(), 2)
        self.assertEqual(OrderEmailState.get().last_checked_date, '2026-09-07')

    def test_import_is_idempotent(self):
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_order_emails', '--path', str(path))
        call_command('import_order_emails', '--path', str(path))

        self.assertEqual(OrderEmailOrder.objects.count(), 1)
        self.assertEqual(OrderEmailMessage.objects.count(), 2)

    def test_checked_date_never_moves_backwards(self):
        marks = OrderEmailState.get()
        marks.last_checked_date = '2026-09-08'
        marks.save()
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_order_emails', '--path', str(path))

        self.assertEqual(OrderEmailState.get().last_checked_date, '2026-09-08')

    def test_empty_file_is_refused(self):
        path = _state_file({'processed_message_ids': [], 'orders': {}})
        self.addCleanup(path.unlink)

        with self.assertRaisesRegex(CommandError, 'ни заказов, ни писем'):
            call_command('import_order_emails', '--path', str(path))


class EmptyJournalPageTests(TestCase):
    """«Демон ещё ни разу не запускался» — про отсутствие журнала, а не про
    журнал, из которого кнопкой удалили последний заказ."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.client.force_login(
            User.objects.create_superuser('admin', 'admin@example.com', 'password'))

    def test_page_says_no_data_until_the_first_run(self):
        response = self.client.get('/api/site-orders/')

        self.assertEqual(response.json()['status'], 'no_data')

    def test_empty_journal_after_a_run_is_not_no_data(self):
        with state_lock():
            save_state({'processed_message_ids': [], 'orders': {},
                        'last_checked_date': '2026-09-07'})

        response = self.client.get('/api/site-orders/')

        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(response.json()['data']['rows'], [])


class OrderEmailStoreTests(TestCase):
    def test_round_trip_keeps_the_shape_the_robots_expect(self):
        save_state(STATE)

        self.assertEqual(load_state({}), STATE)

    def test_forgetting_an_order_removes_it_and_its_messages(self):
        """Страница «Заказы сайта» убирает заказ из журнала — и письмо должно
        разобраться заново при следующей проверке почты."""
        save_state(STATE)

        forgotten = forget_order('535513316')

        self.assertIsNotNone(forgotten)
        self.assertEqual(OrderEmailOrder.objects.count(), 0)
        self.assertEqual(list(OrderEmailMessage.objects.values_list('message_id', flat=True)),
                         ['<b@site.m>'], 'письмо забытого заказа отпущено, чужое осталось')

    def test_empty_journal_does_not_wipe_the_only_copy(self):
        save_state(STATE)

        save_state({'processed_message_ids': [], 'orders': {}, 'last_checked_date': '2026-09-08'})

        self.assertEqual(OrderEmailOrder.objects.count(), 1)
        self.assertEqual(OrderEmailState.get().last_checked_date, '2026-09-08')

    def test_lock_is_reentrant_enough_for_a_single_process(self):
        """Вне Postgres замок — пустышка: процесс там один. Проверяем, что он
        хотя бы не мешает работать."""
        with state_lock():
            save_state(STATE)

        self.assertEqual(OrderEmailOrder.objects.count(), 1)

    def test_last_checked_at_replaces_the_file_mtime(self):
        save_state(STATE)

        self.assertIsNotNone(last_checked_at())
