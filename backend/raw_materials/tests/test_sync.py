from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests

from django.test import TestCase

from core.models import RawMaterial
from raw_materials.models import Batch, BatchMovement, MaterialStock, Slot, SlotStock
from raw_materials.services.sync import sync_from_moysklad
from raw_materials.tests.factories import batch, material

MS = 'raw_materials.services.moysklad'


class SyncTests(TestCase):
    def run_sync(self, stock, placed=None, product=None, recalculating=(), **kwargs):
        product_patch = {'side_effect': product} if isinstance(product, Exception) else {'return_value': product or {}}
        with patch(f'{MS}.store_id', return_value='store'), \
                patch(f'{MS}.slots', return_value={'s-a5': 'A5', 's-b7': 'B7'}), \
                patch(f'{MS}.stock', return_value=(stock, set(recalculating))), \
                patch(f'{MS}.slot_stock', return_value={k: {v: 1} for k, v in (placed or {}).items()}), \
                patch(f'{MS}.product', **product_patch) as fetch:
            result = sync_from_moysklad(**kwargs)
        return result, fetch

    def test_stock_and_slot_come_from_moysklad(self):
        chondroitin = material()
        self.run_sync({chondroitin.external_id: 1500.5}, {chondroitin.external_id: 's-a5'})
        stock = MaterialStock.objects.get(material=chondroitin)
        self.assertEqual((stock.quantity, stock.slot.name), (Decimal('1500.5'), 'A5'))
        self.assertEqual(Slot.objects.count(), 2)

    def test_unknown_material_is_created_from_the_product_card(self):
        product = {'name': 'Крышка 110 мм', 'uom': {'name': 'шт'}, 'pathName': 'Тара'}
        _, fetch = self.run_sync({'new-id': 40}, product=product)
        fetch.assert_called_once_with('new-id')
        self.assertEqual(RawMaterial.objects.get(external_id='new-id').name, 'Крышка 110 мм')

    def test_known_material_does_not_hit_the_product_card(self):
        chondroitin = material()
        _, fetch = self.run_sync({chondroitin.external_id: 10})
        fetch.assert_not_called()

    def test_material_gone_from_moysklad_keeps_its_slot_and_loses_batches(self):
        chondroitin = material()
        batch(chondroitin, '100', series='A')
        self.run_sync({chondroitin.external_id: 100}, {chondroitin.external_id: 's-b7'})

        result, _ = self.run_sync({})

        stock = MaterialStock.objects.get(material=chondroitin)
        self.assertEqual((stock.quantity, stock.slot.name), (Decimal('0'), 'B7'))
        self.assertEqual(Batch.objects.get().quantity, Decimal('0'))
        self.assertEqual(result['corrected'], 1)

    def test_material_being_recalculated_keeps_its_series(self):
        chondroitin = material()
        batch(chondroitin, '100', series='A')
        self.run_sync({chondroitin.external_id: 100})

        result, _ = self.run_sync({}, recalculating=[chondroitin.external_id])

        self.assertEqual(Batch.objects.get().quantity, Decimal('100'))
        self.assertEqual(result['skipped'], 1)

    def test_variant_on_the_shelf_does_not_break_the_sync(self):
        chondroitin = material()
        missing = requests.HTTPError(response=MagicMock(status_code=404))
        result, _ = self.run_sync({chondroitin.external_id: 10, 'variant-id': 5}, product=missing)
        self.assertEqual(result['materials'], 1)
        self.assertFalse(MaterialStock.objects.filter(material__external_id='variant-id').exists())

    def test_cut_after_import_is_marked_as_import(self):
        chondroitin = material()
        batch(chondroitin, '100', series='A')
        self.run_sync({chondroitin.external_id: 60}, kind=BatchMovement.IMPORT)
        self.assertEqual(BatchMovement.objects.get().kind, BatchMovement.IMPORT)

    def test_every_slot_is_kept_and_the_fullest_becomes_home(self):
        chondroitin = material()
        with patch(f'{MS}.store_id', return_value='store'), \
                patch(f'{MS}.slots', return_value={'s-a5': 'A5', 's-b7': 'B7'}), \
                patch(f'{MS}.stock', return_value=({chondroitin.external_id: 180}, set())), \
                patch(f'{MS}.slot_stock', return_value={chondroitin.external_id: {'s-a5': 80, 's-b7': 100}}):
            sync_from_moysklad()
        stock = MaterialStock.objects.get(material=chondroitin)
        self.assertEqual(stock.slot.name, 'B7')
        self.assertEqual(
            sorted((s.slot.name, s.quantity) for s in SlotStock.objects.all()),
            [('A5', Decimal('80')), ('B7', Decimal('100'))],
        )

    def test_material_issued_during_the_read_waits_for_the_next_sync(self):
        chondroitin = material()
        series = batch(chondroitin, '100', series='A')
        self.run_sync({chondroitin.external_id: 100})

        def issued_meanwhile(store):
            BatchMovement.objects.create(batch=series, kind=BatchMovement.ISSUE, quantity=Decimal('-40'))
            Batch.objects.filter(pk=series.pk).update(quantity=Decimal('60'))
            return {chondroitin.external_id: 100}, set()

        with patch(f'{MS}.store_id', return_value='store'), \
                patch(f'{MS}.slots', return_value={}), \
                patch(f'{MS}.stock', side_effect=issued_meanwhile), \
                patch(f'{MS}.slot_stock', return_value={}):
            result = sync_from_moysklad()

        self.assertEqual(Batch.objects.get(pk=series.pk).quantity, Decimal('60'))
        self.assertEqual(result['skipped'], 1)
