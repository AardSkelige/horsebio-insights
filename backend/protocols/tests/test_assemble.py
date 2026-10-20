from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from protocols.models import ManualSeries
from protocols.services.assemble import group_rows, prepare
from protocols.tests.factories import link, material, plan_row, row_material, task, template
from raw_materials.models import Batch, BatchMovement


def batch(material_obj, series, expiry, quantity='100'):
    return Batch.objects.create(
        material=material_obj, series=series, expiry_date=expiry, quantity=Decimal(quantity),
        manufacturer='ВИТАСОЛЬ', received_at=timezone.make_aware(datetime(2026, 1, 1)),
    )


class GroupingTests(TestCase):
    def test_dogs_and_horses_share_one_protocol_when_together(self):
        dogs = template('Хондрофит для собак')
        horses = template('Хондрофит для лошадей', merge_into=dogs)
        link('p-dog', dogs)
        link('p-horse', horses)

        together = group_rows(task(plan_row('p-dog', [], []), plan_row('p-horse', [], [])))
        alone = group_rows(task(plan_row('p-horse', [], [])))

        self.assertEqual([g['template'] for g in together], [dogs])
        self.assertEqual([g['template'] for g in alone], [horses])

    def test_unlinked_plan_has_no_template(self):
        self.assertIsNone(group_rows(task(plan_row('p-new', [], [])))[0]['template'])


class VariantTests(TestCase):
    def setUp(self):
        self.chondroitin = material('Хондроитин сульфат', 'm-ch')
        self.flavor = material('Ароматизатор Говядина', 'm-fl')
        material('Ведро 2 литра', 'm-bucket', group='Тара', uom='шт')
        self.template = template('Хондро', rows=['Хондроитин сульфат', 'Ароматизатор', 'Вода'])
        row_material(self.template, 'Хондроитин сульфат', self.chondroitin)
        row_material(self.template, 'Ароматизатор', self.flavor)
        link('p-1', self.template)
        self.task = task(plan_row('p-1', [('Хондро 600 г', 20)], [
            ('m-ch', 'Хондроитин сульфат', 2310),
            ('m-bucket', 'Ведро 2 литра', 20),
            ('m-label', 'Наклейка Хондро 600г', 20),
        ]))

    def test_rows_follow_the_template_and_take_qty_from_the_task(self):
        rows = {r['row_name']: r for r in prepare(self.task)[0]['rows']}
        self.assertEqual(list(rows), ['Хондроитин сульфат', 'Ароматизатор'])
        self.assertEqual(rows['Хондроитин сульфат']['qty'], 2310)
        self.assertEqual(rows['Ароматизатор']['qty'], 0)

    def test_labels_and_tara_are_separated(self):
        variant = prepare(self.task)[0]
        self.assertEqual([l['source_name'] for l in variant['labels']], ['Наклейка Хондро 600г'])
        self.assertEqual([(u['name'], u['is_tara']) for u in variant['unplaced']], [('Ведро 2 литра', True)])

    def test_series_last_issued_wins_over_soonest_on_shelf(self):
        old = batch(self.chondroitin, 'OLD', date(2027, 1, 1))
        batch(self.chondroitin, 'NEW', date(2028, 1, 1))
        BatchMovement.objects.create(batch=old, kind=BatchMovement.RECONCILE, quantity=Decimal('-10'))
        batch(self.chondroitin, 'SOON', date(2026, 12, 1))

        row = prepare(self.task)[0]['rows'][0]

        self.assertEqual((row['series'], row['source']), ('OLD', 'issued'))
        self.assertEqual([o['series'] for o in row['options']], ['SOON', 'OLD', 'NEW'])

    def test_soonest_on_shelf_when_nothing_was_issued(self):
        batch(self.chondroitin, 'LATE', date(2028, 1, 1))
        batch(self.chondroitin, 'SOON', date(2027, 1, 1))
        self.assertEqual(prepare(self.task)[0]['rows'][0]['series'], 'SOON')

    def test_manual_series_is_flagged_when_expired_on_task_date(self):
        ManualSeries.objects.create(material=self.flavor, series='25095796', expiry_date=date(2026, 9, 23))
        flavor = prepare(self.task)[0]['rows'][1]
        self.assertEqual((flavor['series'], flavor['source'], flavor['expired']), ('25095796', 'manual', True))
