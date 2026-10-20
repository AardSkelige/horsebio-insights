from decimal import Decimal

from django.test import TestCase

from raw_materials.models import Batch, BatchMovement
from raw_materials.services.reconcile import reconcile
from raw_materials.tests.factories import batch, material, stock


class ReconcileTests(TestCase):
    def setUp(self):
        self.material = material()

    def quantities(self):
        return {b.series: b.quantity for b in Batch.objects.filter(material=self.material)}

    def test_matching_total_changes_nothing(self):
        batch(self.material, '100', series='A')
        reconcile(stock(self.material, '100.0004'))
        self.assertFalse(BatchMovement.objects.exists())

    def test_unassigned_is_taken_last_because_it_is_the_fresh_receipt(self):
        batch(self.material, '100', series='A', expiry=(2026, 12, 1))
        batch(self.material, '30')
        reconcile(stock(self.material, '110'))
        self.assertEqual(self.quantities(), {'A': Decimal('80'), '': Decimal('30')})

    def test_shortage_then_goes_by_expiry_with_undated_last(self):
        batch(self.material, '50', series='late', expiry=(2028, 1, 1))
        batch(self.material, '50', series='soon', expiry=(2027, 1, 1))
        batch(self.material, '50', series='no-date')
        reconcile(stock(self.material, '70'))
        self.assertEqual(self.quantities(), {'late': Decimal('20'), 'soon': Decimal('0'), 'no-date': Decimal('50')})

    def test_surplus_lands_in_unassigned(self):
        batch(self.material, '100', series='A')
        reconcile(stock(self.material, '125'))
        self.assertEqual(self.quantities(), {'A': Decimal('100'), '': Decimal('25')})
        self.assertEqual(BatchMovement.objects.get().quantity, Decimal('25'))

    def test_surplus_reuses_existing_unassigned(self):
        batch(self.material, '10')
        reconcile(stock(self.material, '15'))
        self.assertEqual(self.quantities(), {'': Decimal('15')})

    def test_negative_stock_in_moysklad_empties_batches(self):
        batch(self.material, '10', series='A')
        reconcile(stock(self.material, '-3'))
        self.assertEqual(self.quantities(), {'A': Decimal('0')})
