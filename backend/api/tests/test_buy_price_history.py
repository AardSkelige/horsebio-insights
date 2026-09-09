"""
История прогонов робота закупочных цен в базе.

История показывает, что и когда робот поменял в ценах. Восстановить её неоткуда:
файл на томе был единственной копией.
"""
import os
import sys

from django.test import TestCase

from api.models import BuyPriceSyncRun

_HORSEBIO = os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio')
sys.path.insert(0, os.path.join(_HORSEBIO, '_shared'))

from buy_prices_store import DbStore  # noqa: E402

RUNS = [
    {'date': '2026-09-06 00:50', 'stats': {'updated': 2, 'errors': 0},
     'changes': [{'name': 'Коллаген', 'old': 100, 'new': 120}], 'errors': []},
    {'date': '2026-09-07 00:50', 'stats': {'updated': 1, 'errors': 0},
     'changes': [], 'errors': []},
]
STATE = {'last_run': '2026-09-07 00:50', 'last_stats': RUNS[1]['stats'], 'history': RUNS}


class BuyPricesDbStoreTests(TestCase):
    def test_round_trip_keeps_the_shape_the_robot_expects(self):
        store = DbStore()

        store.save(STATE)
        loaded = store.load()

        self.assertEqual(loaded['history'], RUNS)
        self.assertEqual(loaded['last_run'], '2026-09-07 00:50',
                         'последний прогон — просто последняя строка, второй копии ему незачем')
        self.assertEqual(loaded['last_stats'], RUNS[1]['stats'])

    def test_empty_history_reads_as_a_fresh_start(self):
        self.assertEqual(DbStore().load(),
                         {'last_run': None, 'last_stats': {}, 'history': []})

    def test_runs_dropped_by_the_robot_leave_the_database(self):
        """Робот подрезает историю до 90 прогонов, выкидывая старые из списка.
        Если база их сохранит, следующая загрузка воскресит выкинутое."""
        store = DbStore()
        store.save(STATE)

        store.save({'history': RUNS[1:]})

        self.assertEqual(list(BuyPriceSyncRun.objects.values_list('date', flat=True)),
                         ['2026-09-07 00:50'])

    def test_a_run_written_by_someone_else_survives(self):
        """Ручной запуск и плановый пересекаются: оба прочитали историю до,
        и сохраняющий вторым не должен снести прогон первого — восстановить
        историю изменений цен неоткуда."""
        store = DbStore()
        store.save(STATE)
        BuyPriceSyncRun.objects.create(date='2026-09-07 09:05', stats={'updated': 5},
                                       changes=[], errors=[])

        store.save(STATE)  # этот прочитал историю до чужой записи

        self.assertEqual(sorted(BuyPriceSyncRun.objects.values_list('date', flat=True)),
                         ['2026-09-06 00:50', '2026-09-07 00:50', '2026-09-07 09:05'])

    def test_empty_history_does_not_wipe_the_only_copy(self):
        store = DbStore()
        store.save(STATE)

        store.save({'last_run': None, 'last_stats': {}, 'history': []})

        self.assertEqual(BuyPriceSyncRun.objects.count(), 2)

    def test_history_comes_back_in_chronological_order(self):
        """Робот пишет дату как `%Y-%m-%d %H:%M`, и такие строки сортируются
        как даты. Последний прогон — тот, что позже всех, а не тот, что записан
        последним: иначе в отчёте окажутся числа чужого прогона."""
        store = DbStore()
        store.save({'history': [
            {'date': '2026-10-01 00:50', 'stats': {'updated': 3}, 'changes': [], 'errors': []},
            {'date': '2026-09-07 09:05', 'stats': {'updated': 1}, 'changes': [], 'errors': []},
            {'date': '2026-09-07 10:00', 'stats': {'updated': 2}, 'changes': [], 'errors': []},
        ]})

        loaded = store.load()

        self.assertEqual([run['date'] for run in loaded['history']],
                         ['2026-09-07 09:05', '2026-09-07 10:00', '2026-10-01 00:50'])
        self.assertEqual(loaded['last_run'], '2026-10-01 00:50')
        self.assertEqual(loaded['last_stats'], {'updated': 3})
