"""
Один товар двумя строками в документе — это две строки, а не одна.

Так бывает, когда партию принимают двумя поставками с разной ценой или
отгружают из разных партий. Прежде позиция искалась по паре «документ + товар»,
и вторая строка не добавлялась, а перезаписывала первую: приёмка 00242
от 16.12.2024 показывала 1500 банок вместо 4800, а по базе 140 документов
недосчитались 659 тыс. ₽ — при том, что сумма самого документа была верной,
и расхождение ничем себя не выдавало.
"""
from decimal import Decimal
from unittest.mock import Mock, patch

from asgiref.sync import async_to_sync
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Counterparty, Product, RawMaterial, Shipment, ShipmentItem, Supply, SupplyItem,
)


def _position(position_id, assortment_id, quantity, price_kopecks):
    return {
        'id': position_id,
        'quantity': quantity,
        'price': price_kopecks,
        'assortment': {'id': assortment_id, 'name': 'Банка 600 мл'},
    }


class SupplyDuplicateLinesTests(TestCase):
    def setUp(self):
        self.counterparty = Counterparty.objects.create(name='Поставщик', external_id='c-1')
        self.supply = Supply.objects.create(
            counterparty=self.counterparty, external_id='s-1', number='00242',
            date=timezone.now(), sum=Decimal('225600'),
        )
        self.material = RawMaterial.objects.create(name='Банка 600 мл', external_id='m-1', group='Тара')

    def _save(self, position):
        from sync.processors.supplies import SupplyStorage

        storage = SupplyStorage(product_cache=Mock())
        with patch.object(storage, 'product_cache') as cache:
            cache.get_product_details.return_value = {'pathName': 'Тара', 'uom': {'name': 'шт'}}
            return async_to_sync(storage.save_supply_item)(
                self.supply, {'id': 'm-1', 'name': 'Банка 600 мл'}, position, Mock()
            )

    def test_two_lines_of_one_material_stay_two_rows(self):
        self._save(_position('pos-1', 'm-1', 3300, 4700))
        self._save(_position('pos-2', 'm-1', 1500, 4700))

        items = SupplyItem.objects.filter(supply=self.supply)
        self.assertEqual(items.count(), 2, 'вторая строка перезаписала первую')
        self.assertEqual(sum(i.quantity for i in items), Decimal('4800.00'))
        self.assertEqual(sum(i.total for i in items), Decimal('225600.00'))

    def test_same_line_synced_twice_is_updated_not_doubled(self):
        self._save(_position('pos-1', 'm-1', 3300, 4700))
        self._save(_position('pos-1', 'm-1', 3400, 4700))

        items = SupplyItem.objects.filter(supply=self.supply)
        self.assertEqual(items.count(), 1, 'повторная синхронизация задвоила строку')
        self.assertEqual(items.first().quantity, Decimal('3400.00'))


class SupplyPositionWithoutIdTests(TestCase):
    """Строка без идентификатора — редкость, но схлопывать соседей ей нельзя."""

    def setUp(self):
        self.counterparty = Counterparty.objects.create(name='Поставщик', external_id='c-3')
        self.supply = Supply.objects.create(
            counterparty=self.counterparty, external_id='s-2', number='00300',
            date=timezone.now(), sum=Decimal('100'),
        )
        RawMaterial.objects.create(name='Банка 600 мл', external_id='m-1', group='Тара')

    def test_two_lines_without_id_do_not_collapse(self):
        from sync.processors.supplies import SupplyStorage

        storage = SupplyStorage(product_cache=Mock())
        with patch.object(storage, 'product_cache') as cache:
            cache.get_product_details.return_value = {'pathName': 'Тара', 'uom': {'name': 'шт'}}
            for quantity in (10, 5):
                position = _position(None, 'm-1', quantity, 1000)
                position.pop('id')
                async_to_sync(storage.save_supply_item)(
                    self.supply, {'id': 'm-1', 'name': 'Банка 600 мл'}, position, Mock()
                )

        self.assertEqual(SupplyItem.objects.filter(supply=self.supply).count(), 2)


class ShipmentDuplicateLinesTests(TestCase):
    def setUp(self):
        self.counterparty = Counterparty.objects.create(name='Покупатель', external_id='c-2')
        self.shipment = Shipment.objects.create(
            counterparty=self.counterparty, external_id='sh-1', number='00100', date=timezone.now(),
        )
        self.product = Product.objects.create(
            name='Гель', external_id='p-1', group='Товары', subgroup='Гели',
        )

    def _save(self, position):
        from sync.processors.shipments import ShipmentStorage

        storage = ShipmentStorage(product_cache=Mock(), material_registry=Mock())
        storage.material_registry.get_materials_for_product.return_value = []
        with patch.object(storage, 'product_cache') as cache:
            cache.get_product_details.return_value = {'pathName': 'Товары/Гели', 'uom': {'name': 'шт'}}
            return async_to_sync(storage.save_shipment_item)(
                self.shipment, {'id': 'p-1', 'name': 'Гель'}, position, Mock()
            )

    def test_two_lines_of_one_product_stay_two_rows(self):
        self._save(_position('pos-1', 'p-1', 10, 50000))
        self._save(_position('pos-2', 'p-1', 4, 45000))

        items = ShipmentItem.all_objects.filter(shipment=self.shipment)
        self.assertEqual(items.count(), 2, 'вторая строка перезаписала первую')
        self.assertEqual(sum(i.quantity for i in items), Decimal('14.00'))

    def test_cleanup_is_skipped_when_a_position_did_not_save(self):
        """Карточку товара удалили в МойСкладе — позиция не сохранилась.
        Уборка по неполному списку снесла бы живую строку с расходом сырья."""
        from sync.processors.shipments import ShipmentStorage

        self._save(_position('pos-1', 'p-1', 10, 50000))

        storage = ShipmentStorage(product_cache=Mock(), material_registry=Mock())
        with patch.object(storage, 'product_cache') as cache:
            cache.get_product_details.return_value = None
            saved = async_to_sync(storage.save_shipment_item)(
                self.shipment, {'id': 'p-2', 'name': 'Пропавший товар'},
                _position('pos-2', 'p-2', 1, 100), Mock()
            )

        self.assertIsNone(saved, 'позиция без карточки не сохраняется')
        self.assertEqual(ShipmentItem.all_objects.filter(shipment=self.shipment).count(), 1)

    def test_cleanup_removes_lines_gone_from_the_document(self):
        """И заодно позиции без идентификатора строки — наследие до 10.09.2026:
        без уборки они остались бы рядом с новыми и задвоили количество."""
        from sync.processors.shipments import ShipmentStorage

        self._save(_position('pos-1', 'p-1', 10, 50000))
        self._save(_position('pos-2', 'p-1', 4, 45000))
        ShipmentItem.objects.create(
            shipment=self.shipment, product=self.product,
            quantity=Decimal('7'), price=Decimal('500'), external_id=None,
        )

        storage = ShipmentStorage(product_cache=Mock(), material_registry=Mock())
        async_to_sync(storage.cleanup_orphaned_items)(self.shipment, ['pos-1'])

        items = ShipmentItem.all_objects.filter(shipment=self.shipment)
        self.assertEqual([i.external_id for i in items], ['pos-1'])
