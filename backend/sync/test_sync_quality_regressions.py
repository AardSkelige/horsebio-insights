import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import requests
from asgiref.sync import async_to_sync
from django.db import DatabaseError
from django.test import RequestFactory, SimpleTestCase, TestCase

from .cache import ProductCache, ProductDetailsFetchError
from .moysklad.base_client import PaginationMixin
from .moysklad.products import ProductsMixin
from .processors.processing_plans import ProcessingPlanProcessor, ProcessingPlanStorage
from .processors.purchases import PurchaseOrderProcessor, PurchaseOrderStorage
from .processors.shipments import ShipmentProcessor, ShipmentStorage
from .processors.supplies import SupplyProcessor, SupplyStorage
from .sync_task import BaseTask, TaskManager, TaskStatus


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

    @patch('sync.moysklad.products.requests.get')
    def test_product_details_propagates_non_404_error(self, get):
        client = ProductsMixin()
        client.BASE_URL = 'https://example.test'
        client.headers = {}
        get.return_value = response_with_json({}, status_code=503)

        with self.assertRaises(requests.HTTPError):
            client.get_product_details('product-id')

    @patch('sync.moysklad.products.requests.get')
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


class FailingTask(BaseTask):
    async def run(self):
        raise RuntimeError('task failed')


class TaskManagerLifecycleTests(SimpleTestCase):
    def setUp(self):
        self.manager = TaskManager()
        self.manager._initialize()

    def tearDown(self):
        self.manager._initialize()

    def test_terminal_error_is_available_after_worker_cleanup(self):
        task = FailingTask()
        async_to_sync(self.manager._run_task)(task)
        self.manager._current_task = task
        self.manager._is_running = True

        self.manager._cleanup()

        self.assertFalse(self.manager.is_task_running())
        self.assertEqual(self.manager.get_current_state()['status'], 'error')
        self.assertEqual(self.manager.get_current_state()['error'], 'task failed')

    def test_stop_is_cooperative_and_does_not_cleanup_foreign_loop(self):
        task = FailingTask()
        self.manager._current_task = task
        self.manager._is_running = True
        self.manager._thread = MagicMock()

        with patch.object(self.manager, '_cleanup') as cleanup:
            result = self.manager.stop_current_task()

        self.assertEqual(result['status'], 'success')
        self.assertTrue(task.should_stop())
        self.assertEqual(task.progress.status, TaskStatus.STOPPED)
        cleanup.assert_not_called()


class ProgressStreamTests(SimpleTestCase):
    @patch('sync.views.time.sleep', return_value=None)
    @patch('sync.views.task_manager')
    def test_missing_state_is_not_reported_as_success(self, manager, _sleep):
        from .views import stream_loading_progress

        manager.get_current_state.return_value = None
        manager.is_task_running.return_value = False
        response = stream_loading_progress(RequestFactory().get('/parser/stream-progress/'))
        payload = json.loads(next(iter(response.streaming_content)).decode().removeprefix('data: '))

        self.assertEqual(payload['status'], 'error')
        self.assertNotEqual(payload['status'], 'completed')
