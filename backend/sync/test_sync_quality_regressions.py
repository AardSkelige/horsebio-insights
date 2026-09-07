import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import requests
from asgiref.sync import async_to_sync
from django.db import DatabaseError
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils.timezone import make_aware

from .cache import ProductCache, ProductDetailsFetchError
from .models import (
    Counterparty,
    Product,
    RawMaterial,
    RawMaterialUsage,
    Shipment,
    ShipmentItem,
)
from .moysklad.base_client import PaginationMixin
from .moysklad.products import ProductsMixin
from .processors.processing_plans import ProcessingPlanProcessor, ProcessingPlanStorage
from .processors.purchases import PurchaseOrderProcessor, PurchaseOrderStorage
from .processors.shipments import ShipmentProcessor, ShipmentStorage
from .processors.supplies import SupplyProcessor, SupplyStorage
from .sync_task import BaseTask, TaskStatus


def response_with_json(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    return response


class MoySkladClientFailureTests(SimpleTestCase):
    def test_paginated_request_does_not_return_first_page_after_later_failure(self):
        client = PaginationMixin()
        client.headers = {}
        client.get = MagicMock(side_effect=[
            response_with_json({'rows': [{'id': 'first'}]}),
            requests.ConnectionError('connection lost'),
        ])

        with self.assertRaisesRegex(requests.ConnectionError, 'connection lost'):
            client.paginated_request('/products', limit=1)

    def test_single_request_propagates_invalid_json(self):
        client = PaginationMixin()
        client.headers = {}
        response = response_with_json({})
        response.json.side_effect = requests.JSONDecodeError('bad json', 'x', 0)
        client.get = MagicMock(return_value=response)

        with self.assertRaises(requests.JSONDecodeError):
            client.single_request('/product/1')

    @patch('sync.moysklad.products.ms_http.get')
    def test_product_details_propagates_non_404_error(self, get):
        client = ProductsMixin()
        client.BASE_URL = 'https://example.test'
        client.headers = {}
        get.return_value = response_with_json({}, status_code=503)

        with self.assertRaises(requests.HTTPError):
            client.get_product_details('product-id')

    @patch('sync.moysklad.products.ms_http.get')
    def test_product_details_returns_empty_only_when_product_and_variant_are_absent(self, get):
        client = ProductsMixin()
        client.BASE_URL = 'https://example.test'
        client.headers = {}
        get.side_effect = [
            response_with_json({}, status_code=404),
            response_with_json({}, status_code=404),
        ]

        self.assertEqual(client.get_product_details('missing-id'), {})
        self.assertEqual(get.call_count, 2)

    def test_transient_product_failure_is_not_negative_cached(self):
        client = MagicMock()
        client.get_product_details.side_effect = [
            requests.ConnectionError('temporary'),
            {'id': 'product-id', 'name': 'Product'},
        ]
        product_cache = ProductCache()

        with self.assertRaisesRegex(ProductDetailsFetchError, 'temporary'):
            product_cache.get_product_details(client, 'product-id')

        self.assertNotIn('product-id', product_cache.missed_products)
        self.assertEqual(
            product_cache.get_product_details(client, 'product-id'),
            {'id': 'product-id', 'name': 'Product'},
        )
        self.assertEqual(client.get_product_details.call_count, 2)


class ProcessorFailureTests(SimpleTestCase):
    def task(self):
        task = MagicMock()
        task.should_stop.return_value = False
        return task

    def assert_process_reraises(self, processor, call, *args):
        with self.assertRaisesRegex(RuntimeError, 'upstream failed'):
            async_to_sync(call)(*args)
        processor.task_instance.update_progress.assert_any_call(
            status=TaskStatus.ERROR,
            message=ANY,
            error='upstream failed',
        )

    def test_processing_plan_failure_is_not_swallowed(self):
        client = MagicMock()
        client.get_all_processing_plans.side_effect = RuntimeError('upstream failed')
        processor = ProcessingPlanProcessor(client, ProductCache(), self.task())
        self.assert_process_reraises(processor, processor.process)

    def test_purchase_failure_is_not_swallowed(self):
        client = MagicMock()
        client.get_purchase_orders_for_period.side_effect = RuntimeError('upstream failed')
        processor = PurchaseOrderProcessor(client, ProductCache(), self.task())
        self.assert_process_reraises(
            processor,
            processor.process,
            [self._time_range()],
        )

    def test_supply_failure_is_not_swallowed(self):
        client = MagicMock()
        client.get_supplies_for_period.side_effect = RuntimeError('upstream failed')
        processor = SupplyProcessor(client, ProductCache(), self.task())
        self.assert_process_reraises(
            processor,
            processor.process,
            [self._time_range()],
        )

    def test_shipment_failure_is_not_swallowed(self):
        client = MagicMock()
        client.get_shipments_for_period.side_effect = RuntimeError('upstream failed')
        registry = MagicMock()
        registry.load_existing_materials = AsyncMock()
        processor = ShipmentProcessor(client, ProductCache(), registry, self.task())
        self.assert_process_reraises(
            processor,
            processor.process,
            [self._time_range()],
        )

    @staticmethod
    def _time_range():
        from datetime import datetime
        return datetime(2026, 1, 1), datetime(2026, 2, 1)


class StorageDatabaseFailureTests(TestCase):
    def test_storage_layers_propagate_database_errors(self):
        cases = [
            (
                ProcessingPlanStorage(ProductCache()).save_processing_plan,
                {'id': 'plan', 'name': 'Plan'},
                'sync.processors.processing_plans.ProcessingPlan.objects.update_or_create',
            ),
            (
                PurchaseOrderStorage(ProductCache()).save_purchase_order_data,
                ({'id': 'order'}, {'id': 'agent'}),
                'sync.processors.purchases.Counterparty.objects.get_or_create',
            ),
            (
                SupplyStorage(ProductCache()).save_supply_data,
                ({'id': 'supply'}, {'id': 'agent'}),
                'sync.processors.supplies.Counterparty.objects.get_or_create',
            ),
            (
                ShipmentStorage(ProductCache(), MagicMock()).save_shipment_data,
                ({'id': 'shipment'}, {'id': 'agent'}),
                'sync.processors.shipments.Counterparty.objects.get_or_create',
            ),
        ]

        for method, args, target in cases:
            with self.subTest(target=target), patch(target, side_effect=DatabaseError('db down')):
                if not isinstance(args, tuple):
                    args = (args,)
                with self.assertRaisesRegex(DatabaseError, 'db down'):
                    async_to_sync(method)(*args)


class ShipmentSoftDeleteTests(TestCase):
    """Отгрузка, пропавшая из выгрузки, помечается, а не стирается.

    Стирание уносило каскадом её позиции и расход сырья, и достаточно было
    одного периода, где МойСклад отдал неполный список, чтобы связи оборвались
    без следа: вернуть их мог только повторный синк, а заметить пропажу — никто.
    """

    def setUp(self):
        self.counterparty = Counterparty.objects.create(external_id='agent', name='ООО «Ромашка»')
        self.product = Product.objects.create(external_id='product', name='Коллаген')
        self.material = RawMaterial.objects.create(external_id='material', name='Желатин')
        self.shipment = Shipment.objects.create(
            external_id='shipment',
            number='00042',
            date=make_aware(datetime(2026, 1, 15)),
            counterparty=self.counterparty,
        )
        self.item = ShipmentItem.objects.create(
            shipment=self.shipment, product=self.product,
            quantity=Decimal('2'), price=Decimal('100'),
        )
        RawMaterialUsage.objects.create(
            shipment_item=self.item, raw_material=self.material, quantity=Decimal('4'),
        )

    def _sync_period_without_shipments(self):
        """Прогон периода, в котором МойСклад не вернул ни одного документа."""
        client = MagicMock()
        client.get_shipments_for_period.return_value = []
        registry = MagicMock()
        registry.load_existing_materials = AsyncMock()
        task = MagicMock()
        task.should_stop.return_value = False
        processor = ShipmentProcessor(client, ProductCache(), registry, task)
        async_to_sync(processor.process)([(
            make_aware(datetime(2026, 1, 1)), make_aware(datetime(2026, 2, 1)),
        )])

    def test_missing_shipment_is_marked_and_keeps_its_links(self):
        self._sync_period_without_shipments()

        self.assertEqual(Shipment.all_objects.count(), 1)
        self.assertIsNotNone(Shipment.all_objects.get().deleted_at)
        self.assertEqual(ShipmentItem.all_objects.count(), 1)
        self.assertEqual(RawMaterialUsage.all_objects.count(), 1)

    def test_marked_shipment_disappears_from_reports(self):
        """Пометка бесполезна, если позиции продолжают считаться: аналитика
        и прогнозы ходят в позиции напрямую, минуя отгрузку."""
        self._sync_period_without_shipments()

        self.assertEqual(Shipment.objects.count(), 0)
        self.assertEqual(ShipmentItem.objects.count(), 0)
        # Расход сырья считают прямо по нему, минуя и отгрузку, и позицию:
        # страницы материалов и закупок, оптимизатор закупок.
        self.assertEqual(RawMaterialUsage.objects.count(), 0)

    def test_marked_shipment_is_still_reachable_through_its_item(self):
        """Обход связей пометка ломать не должна — иначе она прячет документ
        не только из отчётов, но и из самой синхронизации."""
        self._sync_period_without_shipments()

        item = ShipmentItem.all_objects.get()
        self.assertEqual(item.shipment.number, '00042')

    def test_returned_shipment_loses_the_mark(self):
        """Документ вернулся в выгрузку — пометка снимается, дубль не заводится."""
        Shipment.all_objects.update(deleted_at=make_aware(datetime(2026, 2, 1)))
        storage = ShipmentStorage(ProductCache(), MagicMock())

        async_to_sync(storage.save_shipment_data)(
            {'id': 'shipment', 'name': '00042', 'moment': '2026-01-15 10:00:00'},
            {'id': 'agent', 'name': 'ООО «Ромашка»'},
        )

        self.assertEqual(Shipment.all_objects.count(), 1)
        shipment = Shipment.all_objects.get()
        self.assertIsNone(shipment.deleted_at)
        self.assertIsNotNone(shipment.last_seen_at)


class FailingTask(BaseTask):
    async def run(self):
        raise RuntimeError('task failed')


class TaskStatusTests(TestCase):
    """Отсутствие состояния не должно выглядеть успехом.

    Раньше это проверялось на потоке прогресса: он отдавал `completed`, когда
    состояние задачи пропадало, и полоса «доезжала» у мёртвой задачи. Поток
    убран, состояние живёт в базе — свойство проверяем на её месте.
    """

    def test_missing_state_is_not_reported_as_success(self):
        from django.contrib.auth.models import User
        from django.test import Client

        client = Client()
        client.force_login(User.objects.create_user('user', password='password'))

        payload = client.get('/parser/task-status/').json()

        self.assertFalse(payload['is_running'])
        self.assertIsNone(payload['state'])
