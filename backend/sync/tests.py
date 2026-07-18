from io import StringIO
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .sync_task import ParserTask, TaskStatus


class ParserTaskMaterialErrorTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch('sync.sync_task.MoySkladAPIClient')
    def test_sync_materials_reraises_client_error(self, client_class):
        client_class.return_value.get_materials_updated_since.side_effect = RuntimeError(
            'MoySklad unavailable'
        )
        task = ParserTask()

        with self.assertRaisesRegex(RuntimeError, 'MoySklad unavailable'):
            async_to_sync(task.sync_materials)()

        self.assertEqual(task.progress.status, TaskStatus.ERROR)
        self.assertEqual(task.progress.error, 'MoySklad unavailable')
        self.assertIsNone(cache.get('last_materials_sync_time'))

    @patch('sync.sync_task.MoySkladAPIClient')
    @patch('sync.processors.shipments.ShipmentProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.supplies.SupplyProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.purchases.PurchaseOrderProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.processing_plans.ProcessingPlanProcessor.process', new_callable=AsyncMock)
    def test_material_error_prevents_success_and_following_stages(
        self,
        processing_plans_process,
        purchase_orders_process,
        supplies_process,
        shipments_process,
        client_class,
    ):
        client_class.return_value.get_materials_updated_since.side_effect = RuntimeError(
            'MoySklad unavailable'
        )
        task = ParserTask()

        async_to_sync(task.run)()

        processing_plans_process.assert_awaited_once()
        purchase_orders_process.assert_not_awaited()
        supplies_process.assert_not_awaited()
        shipments_process.assert_not_awaited()
        self.assertEqual(task.progress.status, TaskStatus.ERROR)
        self.assertEqual(task.progress.error, 'MoySklad unavailable')
        self.assertIsNone(cache.get('last_successful_update'))


class AutoSyncWeeklyCommandTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_command_uses_owned_lock_and_heartbeat(self):
        with (
            patch('sync.management.commands.auto_sync_weekly.SyncLock') as sync_lock,
            patch('sync.management.commands.auto_sync_weekly.SyncLockHeartbeat') as heartbeat_class,
            patch('sync.management.commands.auto_sync_weekly.ParserTask') as task_class,
        ):
            sync_lock.acquire_lock.return_value = 'owner-token'
            task = task_class.return_value
            task.run = AsyncMock()
            task.progress.status = TaskStatus.COMPLETED

            call_command('auto_sync_weekly', stdout=StringIO())

        sync_lock.acquire_lock.assert_called_once_with(
            'moysklad_sync', locked_by='auto_sync_weekly'
        )
        heartbeat_class.assert_called_once_with(task, 'moysklad_sync', 'owner-token')
        heartbeat_class.return_value.start.assert_called_once_with()
        heartbeat_class.return_value.stop.assert_called_once_with()
        sync_lock.release_lock.assert_called_once_with('moysklad_sync', 'owner-token')

    def test_task_error_fails_command_and_does_not_report_success(self):
        output = StringIO()
        with (
            patch('sync.management.commands.auto_sync_weekly.SyncLock') as sync_lock,
            patch('sync.management.commands.auto_sync_weekly.SyncLockHeartbeat') as heartbeat_class,
            patch('sync.management.commands.auto_sync_weekly.ParserTask') as task_class,
        ):
            sync_lock.acquire_lock.return_value = 'owner-token'
            task = task_class.return_value
            task.run = AsyncMock()
            task.progress.status = TaskStatus.ERROR
            task.progress.error = 'MoySklad unavailable'

            with self.assertRaisesRegex(CommandError, 'MoySklad unavailable'):
                call_command('auto_sync_weekly', stdout=output)

        self.assertNotIn('выполнена синхронно', output.getvalue())
        self.assertIsNone(cache.get('last_auto_sync_started'))
        heartbeat_class.return_value.stop.assert_called_once_with()
        sync_lock.release_lock.assert_called_once_with('moysklad_sync', 'owner-token')
