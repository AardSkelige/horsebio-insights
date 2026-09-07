"""
Переезд копии заказов сайта из файла в базу.

Осторожность здесь не лишняя: подтверждённое окно сайт больше не отдаёт,
и эта копия — единственная. Файл на томе держался на том, что том не забыли
смонтировать.
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api.models import SiteOrderSnapshot, SiteOrdersReconcileState

_HORSEBIO = os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio')
sys.path.insert(0, os.path.join(_HORSEBIO, '_shared'))
sys.path.insert(0, os.path.join(_HORSEBIO, '02_checks', '02_site_orders', 'scripts'))

import reconcile_core as core  # noqa: E402
from site_orders_store import DbStore  # noqa: E402

ORDER = {'order_id': '594131116', 'number': '2066', 'date': '2026-08-19',
         'total': 1264, 'paid': True, 'cancelled': False, 'status': 'Оплачен',
         'positions': [{'article': '01-14AP0250', 'name': 'Гель ЮНИФЛЕКС',
                        'price': 836, 'quantity': 1, 'total': 836, 'discounts': []}]}

STORE = {'orders': {'594131116': ORDER},
         'last_fetch': '2026-09-06T09:00:00',
         'last_acknowledge': '2026-09-06T09:00:01'}


def _store_file(data=None):
    tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
    json.dump(STORE if data is None else data, tmp, ensure_ascii=False)
    tmp.close()
    return Path(tmp.name)


class ImportSiteOrdersTests(TestCase):
    def test_import_moves_orders_and_marks(self):
        path = _store_file()
        self.addCleanup(path.unlink)

        call_command('import_site_orders', '--path', str(path))

        row = SiteOrderSnapshot.objects.get(order_id='594131116')
        self.assertEqual(row.payload['number'], '2066')
        self.assertEqual(row.date, '2026-08-19', 'дата вынесена колонкой — по ней чистят старое')
        marks = SiteOrdersReconcileState.get()
        self.assertEqual(marks.last_fetch, '2026-09-06T09:00:00')
        self.assertEqual(marks.last_acknowledge, '2026-09-06T09:00:01')

    def test_import_is_idempotent(self):
        path = _store_file()
        self.addCleanup(path.unlink)

        call_command('import_site_orders', '--path', str(path))
        call_command('import_site_orders', '--path', str(path))

        self.assertEqual(SiteOrderSnapshot.objects.count(), 1)
        self.assertEqual(SiteOrdersReconcileState.objects.count(), 1)

    def test_dry_run_writes_nothing(self):
        path = _store_file()
        self.addCleanup(path.unlink)

        call_command('import_site_orders', '--path', str(path), '--dry-run')

        self.assertEqual(SiteOrderSnapshot.objects.count(), 0)

    def test_broken_file_is_refused_loudly(self):
        """Молча начать с пустого нельзя: второй копии заказов нет."""
        tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        tmp.write('{"orders": {не json')
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink())

        with self.assertRaisesRegex(CommandError, 'повреждено'):
            call_command('import_site_orders', '--path', tmp.name)

    def test_empty_store_is_refused(self):
        path = _store_file({'orders': {}, 'last_fetch': None, 'last_acknowledge': None})
        self.addCleanup(path.unlink)

        with self.assertRaisesRegex(CommandError, 'нет ни одного заказа'):
            call_command('import_site_orders', '--path', str(path))


class DbStoreTests(TestCase):
    def test_round_trip_keeps_the_shape_the_check_expects(self):
        store = DbStore()

        store.save(STORE)
        loaded = store.load()

        self.assertEqual(loaded, STORE, 'форма словаря должна остаться прежней')

    def test_orders_dropped_from_the_dict_leave_the_database(self):
        """Сверка чистит слишком старые заказы, выкидывая их из словаря.
        Если база их сохранит, следующая загрузка воскресит выкинутое."""
        store = DbStore()
        store.save({'orders': {'594131116': ORDER, 'старый': dict(ORDER, date='2024-01-01')},
                    'last_fetch': None, 'last_acknowledge': None})

        store.save(STORE)  # 'старый' в словаре больше нет

        self.assertEqual(list(SiteOrderSnapshot.objects.values_list('order_id', flat=True)),
                         ['594131116'])

    def test_empty_dict_does_not_wipe_the_only_copy(self):
        """Пустой словарь — форма EMPTY_STORE и чтения отсутствующего файла.
        Принять его за «удалить всё» значило бы стереть единственную копию."""
        store = DbStore()
        store.save(STORE)

        store.save({'orders': {}, 'last_fetch': None, 'last_acknowledge': None})

        self.assertEqual(SiteOrderSnapshot.objects.count(), 1)

    def test_sync_window_works_against_the_database(self):
        """Тот же порядок шагов, что проверен на файле: сохранить, убедиться,
        что запись долетела, и только потом подтвердить окно сайту."""
        class FakeOrder:
            order_id = '594131116'

            def as_dict(self):
                return ORDER

        class FakeExport:
            refused = False

            def __init__(self):
                self.acknowledged = 0

            def fetch(self):
                return [FakeOrder()]

            def acknowledge(self):
                self.acknowledged += 1
                return 'success'

        export = FakeExport()
        result = core.sync_window(export, DbStore(), acknowledge=True,
                                  now=datetime(2026, 9, 6, 9, 0, 0))

        self.assertEqual(result['fresh'], 1)
        self.assertEqual(SiteOrderSnapshot.objects.count(), 1)
        self.assertEqual(SiteOrdersReconcileState.get().last_fetch, '2026-09-06T09:00:00')
        # Окно неполное — подтверждать его нельзя, иначе сайт спишет заказы,
        # которых мы ещё не видели.
        self.assertEqual(export.acknowledged, 0)


class MigrationGuardTests(TestCase):
    """Между выкатом образа и ручным переносом сверка не должна начать
    с чистого листа: «сверено 0 заказов, расхождений нет» выглядит спокойно,
    а на деле означает, что вся история пропала с глаз."""

    def test_legacy_file_with_orders_is_seen(self):
        path = _store_file()
        self.addCleanup(path.unlink)

        self.assertEqual(core.legacy_orders_count(path), 1)

    def test_missing_file_means_nothing_left_behind(self):
        self.assertEqual(core.legacy_orders_count('/nope/site_orders.json'), 0)


class MarksTests(TestCase):
    def test_import_does_not_move_marks_backwards(self):
        """Команду можно запустить и после того, как сверка уже отработала:
        откат отметки назад означал бы находку «сайт молчит» на живом сайте."""
        marks = SiteOrdersReconcileState.get()
        marks.last_fetch = '2026-09-07T09:40:00'
        marks.save()
        path = _store_file()
        self.addCleanup(path.unlink)

        call_command('import_site_orders', '--path', str(path))

        self.assertEqual(SiteOrdersReconcileState.get().last_fetch, '2026-09-07T09:40:00')


class DateColumnTests(TestCase):
    def test_odd_date_does_not_break_the_save(self):
        """Дата приходит из выгрузки сайта и ничем не проверена. Значение длиннее
        колонки уронило бы запись — и роняло бы каждый прогон, пока заказ в окне."""
        store = DbStore()

        store.save({'orders': {'x': dict(ORDER, date='2026-08-19T10:00:00+03:00')},
                    'last_fetch': None, 'last_acknowledge': None})

        row = SiteOrderSnapshot.objects.get(order_id='x')
        self.assertEqual(row.date, '2026-08-19')
        self.assertEqual(row.payload['date'], '2026-08-19T10:00:00+03:00',
                         'в самой записи дата остаётся как пришла')
