from io import StringIO
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import SyncRun
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
            patch('sync.management.commands.auto_sync_weekly.SyncHeartbeat') as heartbeat_class,
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
        # Прогон по расписанию виден в базе: до этого интерфейс о нём не знал
        # ничего — синхронизация шла, а страница показывала «не идёт».
        run = SyncRun.objects.get()
        self.assertEqual(run.triggered_by, 'расписание')
        heartbeat_class.assert_called_once_with(
            task, 'moysklad_sync', 'owner-token', run=run
        )
        heartbeat_class.return_value.start.assert_called_once_with()
        heartbeat_class.return_value.stop.assert_called_once_with()
        sync_lock.release_lock.assert_called_once_with('moysklad_sync', 'owner-token')

    def test_task_error_fails_command_and_does_not_report_success(self):
        output = StringIO()
        with (
            patch('sync.management.commands.auto_sync_weekly.SyncLock') as sync_lock,
            patch('sync.management.commands.auto_sync_weekly.SyncHeartbeat') as heartbeat_class,
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


class TaskStatusFromDatabaseTests(TestCase):
    """`/parser/task-status/` отвечает по записи в базе, а не по памяти
    процесса: под gunicorn воркеров несколько, и спрашивающий попадает
    не обязательно в тот, где идёт задача."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user('user', password='password')
        self.client.force_login(self.user)

    def test_no_runs_yet(self):
        response = self.client.get('/parser/task-status/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['is_running'])
        self.assertIsNone(response.json()['state'])

    def test_running_sync_is_visible_to_everyone(self):
        SyncRun.objects.create(message='Обработка отгрузок', processed=60,
                               triggered_by='расписание')

        payload = self.client.get('/parser/task-status/').json()

        self.assertTrue(payload['is_running'])
        self.assertEqual(payload['state']['message'], 'Обработка отгрузок')
        self.assertEqual(payload['state']['processed'], 60)
        self.assertEqual(payload['state']['triggered_by'], 'расписание')

    def test_abandoned_run_does_not_count_as_running(self):
        """Прогон, оборванный вместе с процессом, остаётся в базе со статусом
        «идёт». Без срока годности он навсегда выключил бы кнопку."""
        from datetime import timedelta
        from django.utils import timezone

        run = SyncRun.objects.create(message='Обработка отгрузок')
        stale = timezone.now() - timedelta(seconds=SyncRun.STALE_AFTER_SECONDS + 5)
        SyncRun.objects.filter(pk=run.pk).update(updated_at=stale)

        self.assertFalse(self.client.get('/parser/task-status/').json()['is_running'])

    def test_finished_run_reports_its_outcome(self):
        from django.utils import timezone
        SyncRun.objects.create(status=SyncRun.STATUS_COMPLETED, message='Готово',
                               processed=100, finished_at=timezone.now())

        payload = self.client.get('/parser/task-status/').json()

        self.assertFalse(payload['is_running'])
        self.assertEqual(payload['state']['status'], SyncRun.STATUS_COMPLETED)
        self.assertIsNotNone(payload['state']['completed_at'])


class SyncHeartbeatMirrorTests(TestCase):
    """Сердцебиение переносит состояние задачи в базу — оттуда его и читают."""

    def _heartbeat(self, run, state):
        from unittest.mock import Mock
        from .sync_task import SyncHeartbeat

        task = Mock()
        task.get_state.return_value = state
        return SyncHeartbeat(task, 'moysklad_sync', 'token', run=run)

    def test_progress_lands_in_the_run_row(self):
        run = SyncRun.objects.create()
        heartbeat = self._heartbeat(run, {
            'status': 'running', 'message': 'Обработка приёмок',
            'processed': 40, 'total': 100, 'error': None,
        })

        heartbeat._mirror_progress()

        run.refresh_from_db()
        self.assertEqual(run.message, 'Обработка приёмок')
        self.assertEqual(run.processed, 40)
        self.assertIsNone(run.finished_at)

    def test_final_state_closes_the_run(self):
        run = SyncRun.objects.create()
        heartbeat = self._heartbeat(run, {
            'status': 'completed', 'message': 'Задача завершена',
            'processed': 100, 'total': 100, 'error': None,
        })

        heartbeat._mirror_progress(final=True)

        run.refresh_from_db()
        self.assertEqual(run.status, SyncRun.STATUS_COMPLETED)
        self.assertIsNotNone(run.finished_at)
        self.assertFalse(run.is_alive)

    def test_broken_row_does_not_break_the_sync(self):
        """Прогон важнее его отображения: не смогли записать — не мешаем."""
        run = SyncRun.objects.create()
        heartbeat = self._heartbeat(run, {'status': 'running', 'message': 'x' * 5000,
                                          'processed': 10, 'total': 100, 'error': None})

        heartbeat._mirror_progress()  # длинное сообщение обрезается, а не падает

        run.refresh_from_db()
        self.assertEqual(len(run.message), 255)


class StopRequestTests(TestCase):
    """«Стоп» просят через базу: нажавший может сидеть в другом процессе,
    а прогон по расписанию идёт вообще отдельной командой."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.client.force_login(User.objects.create_user('user', password='password'))

    def test_stop_marks_the_running_row(self):
        run = SyncRun.objects.create(triggered_by='расписание')

        response = self.client.post('/parser/stop-loading/')

        run.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(run.stop_requested)

    def test_nothing_to_stop_says_so(self):
        response = self.client.post('/parser/stop-loading/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('не выполняется', response.json()['message'])

    def test_heartbeat_passes_the_request_to_the_task(self):
        from unittest.mock import Mock
        from .sync_task import SyncHeartbeat

        run = SyncRun.objects.create()
        SyncRun.objects.filter(pk=run.pk).update(stop_requested=True)
        task = Mock()
        heartbeat = SyncHeartbeat(task, 'moysklad_sync', 'token', run=run)

        heartbeat._check_stop_request()

        task.stop.assert_called_once_with()


class RunLifecycleTests(TestCase):
    def test_task_that_has_not_started_yet_is_not_written_down(self):
        """Первый удар сердца может застать задачу ещё созданной, но не
        запущенной. Записать её статус значило бы объявить прогон
        законченным — а отметку о завершении ставят один раз."""
        from unittest.mock import Mock
        from .sync_task import SyncHeartbeat

        run = SyncRun.objects.create()
        task = Mock()
        task.get_state.return_value = {'status': 'idle', 'message': 'Задача создана',
                                       'processed': 0, 'total': 0, 'error': None}
        heartbeat = SyncHeartbeat(task, 'moysklad_sync', 'token', run=run)

        heartbeat._mirror_progress()

        run.refresh_from_db()
        self.assertEqual(run.status, SyncRun.STATUS_RUNNING)
        self.assertIsNone(run.finished_at)

    def test_old_runs_are_pruned(self):
        for _ in range(SyncRun.KEEP_RUNS + 5):
            SyncRun.start(triggered_by='кнопка')

        self.assertEqual(SyncRun.objects.count(), SyncRun.KEEP_RUNS)
