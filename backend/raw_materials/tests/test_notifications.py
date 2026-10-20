from datetime import date
from unittest.mock import patch

from django.test import TestCase

from api.notifications.raw_materials import expiring_batches
from decimal import Decimal

from raw_materials.models import Slot, SlotStock
from raw_materials.tests.factories import batch, material, stock


class ExpiredBatchNotificationTests(TestCase):
    def test_expired_and_expiring_series_still_on_the_shelf(self):
        multicalcium = material('Витаминная смесь (Мультикальций)')
        stock(multicalcium, '175000', slot=Slot.objects.create(external_id='s', name='B2'))
        expired = batch(multicalcium, '25000', series='119', expiry=(2026, 8, 11))
        batch(multicalcium, '150000', series='379', expiry=(2026, 11, 11))
        batch(multicalcium, '1000', series='fresh', expiry=(2027, 6, 1))
        batch(multicalcium, '0', series='old', expiry=(2025, 1, 1))

        with patch('api.notifications.raw_materials.timezone.localdate', return_value=date(2026, 10, 21)):
            items = list(expiring_batches())

        self.assertEqual([i.level for i in items], ['critical', 'warning'])
        self.assertEqual(items[0].key, f'raw-materials:expired:{expired.id}')
        self.assertEqual(items[1].title, 'Витаминная смесь (Мультикальций) — срок подходит к концу')
        self.assertEqual(items[0].title, 'Витаминная смесь (Мультикальций) — просрочено')
        self.assertEqual(items[0].body, 'Серия 119 · годен до 11.08.2026 · на полке 25 кг · ячейка B2')

    def test_names_every_shelf_and_small_remainders_exactly(self):
        chondroitin = material()
        a6 = Slot.objects.create(external_id='a6', name='A6')
        stock(chondroitin, '0.05', slot=a6)
        SlotStock.objects.create(material=chondroitin, slot=a6, quantity=Decimal('0.03'))
        SlotStock.objects.create(material=chondroitin, slot=Slot.objects.create(external_id='c2', name='C2'), quantity=Decimal('0.02'))
        batch(chondroitin, '0.05', series='X', expiry=(2026, 1, 1))

        with patch('api.notifications.raw_materials.timezone.localdate', return_value=date(2026, 10, 21)):
            body = next(expiring_batches()).body

        self.assertEqual(body, 'Серия X · годен до 01.01.2026 · на полке 0,05 г · ячейки A6, C2')

