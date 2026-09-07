"""
Переезд состояния монитора возвратов из файла в базу.

Отметки «этот заказ уже разобран» — единственное, что не даёт роботу завести
документ возврата дважды: у ВБ и Озона один и тот же возврат приходит несколько
раз. Пропажа тома означала бы повторный разбор всего с START_DATE.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api.models import ReturnProcessedOrder, ReturnsMonitorState

_HORSEBIO = os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio')
sys.path.insert(0, os.path.join(_HORSEBIO, '_shared'))

from returns_store import DbStore  # noqa: E402

MARK = {'order_name': '07688', 'agent': 'Озон', 'status_name': 'Возврат',
        'status': 'no_demand', 'shipped_sum': 0.0, 'processed_at': '2026-05-03T18:12:45'}
STATE = {'last_run': '2026-09-07 00:00:07',
         'processed_orders': {'377da132-6aff': MARK}}


def _state_file(data=None):
    tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
    json.dump(STATE if data is None else data, tmp, ensure_ascii=False)
    tmp.close()
    return Path(tmp.name)


class ImportReturnsStateTests(TestCase):
    def test_import_moves_marks_and_last_run(self):
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_returns_state', '--path', str(path))

        self.assertEqual(ReturnProcessedOrder.objects.get(order_id='377da132-6aff').payload,
                         MARK)
        self.assertEqual(ReturnsMonitorState.get().last_run, '2026-09-07 00:00:07')

    def test_import_is_idempotent(self):
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_returns_state', '--path', str(path))
        call_command('import_returns_state', '--path', str(path))

        self.assertEqual(ReturnProcessedOrder.objects.count(), 1)

    def test_last_run_never_moves_backwards(self):
        """Откат назад заставил бы монитор перебирать уже разобранные заказы."""
        marks = ReturnsMonitorState.get()
        marks.last_run = '2026-09-07 09:00:00'
        marks.save()
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_returns_state', '--path', str(path))

        self.assertEqual(ReturnsMonitorState.get().last_run, '2026-09-07 09:00:00')

    def test_dry_run_writes_nothing(self):
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_returns_state', '--path', str(path), '--dry-run')

        self.assertEqual(ReturnProcessedOrder.objects.count(), 0)

    def test_empty_state_is_refused(self):
        path = _state_file({'last_run': '2026-01-01', 'processed_orders': {}})
        self.addCleanup(path.unlink)

        with self.assertRaisesRegex(CommandError, 'ни одной отметки'):
            call_command('import_returns_state', '--path', str(path))


class ReturnsDbStoreTests(TestCase):
    def test_round_trip_keeps_the_shape_the_monitor_expects(self):
        store = DbStore()

        store.save(STATE)

        self.assertEqual(store.load(), STATE)

    def test_empty_database_falls_back_to_the_start_date(self):
        self.assertEqual(DbStore().load(default_last_run='2026-01-01')['last_run'],
                         '2026-01-01')

    def test_saving_never_removes_marks(self):
        """Монитор отметки не чистит — они только копятся. Удаление по отсутствию
        в словаре стёрло бы полторы тысячи разом на первом же странном прогоне."""
        store = DbStore()
        store.save(STATE)

        store.save({'last_run': '2026-09-07 10:00:00', 'processed_orders': {}})

        self.assertEqual(ReturnProcessedOrder.objects.count(), 1)
        self.assertEqual(ReturnsMonitorState.get().last_run, '2026-09-07 10:00:00')

    def test_force_replaces_marks_together_with_the_new_ones(self):
        """--force разбирает всё заново, и прежние отметки уходят — но одной
        транзакцией с записью новых, а не сбросом до прогона."""
        store = DbStore()
        store.save(STATE)

        store.save({'last_run': '2026-09-07 10:00:00',
                    'processed_orders': {'новый-заказ': MARK}}, replace=True)

        self.assertEqual(list(ReturnProcessedOrder.objects.values_list('order_id', flat=True)),
                         ['новый-заказ'])

    def test_force_that_wrote_nothing_leaves_the_marks_alone(self):
        """Оборвавшийся или ничего не нашедший --force не должен оставить
        робота вовсе без отметок: следующий прогон завёл бы возвраты дублями."""
        store = DbStore()
        store.save(STATE)

        store.save({'last_run': '2026-09-07 10:00:00', 'processed_orders': {}}, replace=True)

        self.assertEqual(ReturnProcessedOrder.objects.count(), 1)

    def test_reset_forgets_everything_explicitly(self):
        """Прогон с --force проверяет всё заново — и это отдельное действие,
        а не побочный эффект обычной записи."""
        store = DbStore()
        store.save(STATE)

        removed = store.reset()

        self.assertEqual(removed, 1)
        self.assertEqual(ReturnProcessedOrder.objects.count(), 0)
