import os
import sys
from datetime import datetime

from django.test import SimpleTestCase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio',
                                '02_checks', '01_health', 'scripts'))

from health_production import rows_detail, stuck_candidates, undone_rows  # noqa: E402

NOW = datetime(2026, 11, 3, 15, 0)


def task(planned, applicable=True, awaiting=True, reserve=True):
    return {'applicable': applicable, 'awaiting': awaiting, 'reserve': reserve,
            'deliveryPlannedMoment': planned, 'moment': '2026-01-01 00:00:00.000'}


def stage(row, position, total, done, skipped=0.0):
    return {'productionRow': {'meta': {'href': row}}, 'orderingPosition': position,
            'totalQuantity': total, 'completedQuantity': done, 'skippedQuantity': skipped}


def product(row, name):
    return {'productionRow': {'meta': {'href': row}}, 'assortment': {'name': name}}


class StuckCandidatesTests(SimpleTestCase):

    def test_plan_older_than_month_with_awaiting_is_candidate(self):
        self.assertEqual(len(stuck_candidates([task('2026-09-03 10:00:00.000')], NOW)), 1)

    def test_reserve_alone_is_enough(self):
        self.assertEqual(len(stuck_candidates([task('2026-03-23 10:00:00.000', awaiting=False)], NOW)), 1)

    def test_fresh_plan_is_skipped(self):
        self.assertEqual(stuck_candidates([task('2026-10-28 10:00:00.000')], NOW), [])

    def test_no_flags_or_not_applicable_is_skipped(self):
        tasks = [task('2026-03-01 10:00:00.000', awaiting=False, reserve=False),
                 task('2026-03-01 10:00:00.000', applicable=False)]
        self.assertEqual(stuck_candidates(tasks, NOW), [])

    def test_exactly_month_is_not_yet_stuck(self):
        self.assertEqual(stuck_candidates([task('2026-10-04 23:00:00.000')], NOW), [])

    def test_day_after_month_is_stuck(self):
        self.assertEqual(len(stuck_candidates([task('2026-10-03 23:00:00.000')], NOW)), 1)

    def test_falls_back_to_document_date(self):
        old = task(None)
        self.assertEqual(len(stuck_candidates([old], NOW)), 1)


class UndoneRowsTests(SimpleTestCase):

    def test_partial_row_reported_with_product(self):
        rows = undone_rows([stage('r1', 0, 30, 30), stage('r2', 0, 110, 106)],
                           [product('r1', 'Мелкие'), product('r2', 'Крупные')])
        self.assertEqual(rows, [{'name': 'Крупные', 'done': 106, 'total': 110}])

    def test_last_stage_decides(self):
        rows = undone_rows([stage('r1', 0, 50, 50), stage('r1', 1, 50, 20)], [product('r1', 'Гель')])
        self.assertEqual(rows, [{'name': 'Гель', 'done': 20, 'total': 50}])

    def test_skipped_quantity_is_not_undone(self):
        self.assertEqual(undone_rows([stage('r1', 0, 110, 106, skipped=4)], [product('r1', 'Гель')]), [])


class RowsDetailTests(SimpleTestCase):

    def test_long_list_is_cut(self):
        rows = [{'name': f'Товар {i}', 'done': 1, 'total': 2} for i in range(5)]
        self.assertEqual(rows_detail(rows), 'Товар 0: сделано 1 из 2, Товар 1: сделано 1 из 2, '
                                            'Товар 2: сделано 1 из 2 и ещё 2')

    def test_short_list_is_whole(self):
        self.assertEqual(rows_detail([{'name': 'Гель', 'done': 20, 'total': 50}]), 'Гель: сделано 20 из 50')
