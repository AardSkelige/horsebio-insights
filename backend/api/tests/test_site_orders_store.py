"""
Копия заказов сайта в базе.

Осторожность здесь не лишняя: подтверждённое окно сайт больше не отдаёт,
и эта копия — единственная. Файл на томе держался на том, что том не забыли
смонтировать.
"""
import os
import sys
from datetime import datetime

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
