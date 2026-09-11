"""Запись расхода сырья при синхронизации отгрузки.

У позиции столько записей расхода, сколько материалов в техкарте, а позиций
в полной синхронизации десятки тысяч — отсюда и полмиллиона строк в таблице.
Поэтому пишем пачкой, и проверять надо две вещи: что числа не изменились и
что число вставок не растёт вместе с техкартой.
"""

from decimal import Decimal
from unittest.mock import Mock, patch

from asgiref.sync import async_to_sync
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import (
    Counterparty, Product, RawMaterial, RawMaterialUsage, Shipment, ShipmentItem,
)


def _position(position_id, product_id, quantity, price):
    return {
        'id': position_id,
        'quantity': quantity,
        'price': price,
        'assortment': {'meta': {'href': f'https://example/entity/product/{product_id}'}},
    }


class MaterialUsageWriteTests(TestCase):
    def setUp(self):
        self.counterparty = Counterparty.objects.create(name='Покупатель', external_id='c-1')
        self.shipment = Shipment.objects.create(
            counterparty=self.counterparty, external_id='sh-1',
            number='00100', date=timezone.now(),
        )
        self.product = Product.objects.create(
            name='Гель', external_id='p-1', group='Товары', subgroup='Гели',
        )

    def recipe(self, count):
        """Техкарта из `count` материалов: по (номер+1) единиц на единицу товара."""
        return [
            {
                'material': RawMaterial.objects.create(
                    name=f'Материал {index}', external_id=f'm-{index}',
                    group='Тара', uom_name='шт',
                ),
                'quantity': index + 1,
            }
            for index in range(count)
        ]

    def save_position(self, materials, quantity=10):
        from sync.processors.shipments import ShipmentStorage

        storage = ShipmentStorage(product_cache=Mock(), material_registry=Mock())
        storage.material_registry.get_materials_for_product.return_value = materials
        with patch.object(storage, 'product_cache') as cache:
            cache.get_product_details.return_value = {
                'pathName': 'Товары/Гели', 'uom': {'name': 'шт'},
            }
            return async_to_sync(storage.save_shipment_item)(
                self.shipment, {'id': 'p-1', 'name': 'Гель'},
                _position('pos-1', 'p-1', quantity, 50000), Mock(),
            )

    def test_usage_rows_keep_their_quantities(self):
        """Расход = норма по техкарте, умноженная на количество в позиции."""
        self.save_position(self.recipe(3), quantity=10)

        rows = {
            usage.raw_material.name: usage.quantity
            for usage in RawMaterialUsage.objects.select_related('raw_material')
        }
        self.assertEqual(rows, {
            'Материал 0': Decimal('10.00'),
            'Материал 1': Decimal('20.00'),
            'Материал 2': Decimal('30.00'),
        })

    def test_empty_recipe_writes_nothing(self):
        """Товар без техкарты расхода не даёт и падать не должен."""
        self.assertIsNotNone(self.save_position([]))
        self.assertEqual(RawMaterialUsage.objects.count(), 0)

    def test_one_insert_regardless_of_recipe_size(self):
        """Две записи и десять — одна вставка, а не вставка на запись."""
        def inserts_for(material_count):
            # Чистим и позицию тоже: при повторном сохранении той же строки
            # синхронизация узнаёт её и до расхода сырья не доходит.
            RawMaterialUsage.all_objects.all().delete()
            ShipmentItem.all_objects.all().delete()
            RawMaterial.objects.all().delete()
            materials = self.recipe(material_count)
            with CaptureQueriesContext(connection) as captured:
                self.save_position(materials)
            return len([
                query for query in captured
                if 'parser_rawmaterialusage' in query['sql'].lower()
                and query['sql'].lower().lstrip().startswith('insert')
            ])

        self.assertEqual(inserts_for(2), 1)
        self.assertEqual(inserts_for(10), 1)
