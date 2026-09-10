import os
import tempfile
from io import StringIO
from unittest.mock import AsyncMock, Mock, patch

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

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
    def test_material_error_does_not_cancel_the_other_entities(
        self,
        processing_plans_process,
        purchase_orders_process,
        supplies_process,
        shipments_process,
        client_class,
    ):
        """Приёмки не виноваты в том, что материалы не отдались: их свежие
        данные нужны сегодня, а не после починки материалов. Раньше падение
        одной сущности отменяло все следующие."""
        client_class.return_value.get_materials_updated_since.side_effect = RuntimeError(
            'MoySklad unavailable'
        )
        task = ParserTask()

        async_to_sync(task.run)()

        processing_plans_process.assert_awaited_once()
        purchase_orders_process.assert_awaited_once()
        supplies_process.assert_awaited_once()
        shipments_process.assert_awaited_once()

    @patch('sync.sync_task.MoySkladAPIClient')
    @patch('sync.processors.shipments.ShipmentProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.supplies.SupplyProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.purchases.PurchaseOrderProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.processing_plans.ProcessingPlanProcessor.process', new_callable=AsyncMock)
    def test_one_failed_entity_makes_the_run_partial(
        self,
        processing_plans_process,
        purchase_orders_process,
        supplies_process,
        shipments_process,
        client_class,
    ):
        """«Частично» — не смягчённая ошибка: маржа уже считается на смеси
        свежего и вчерашнего, и это должно быть видно."""
        client_class.return_value.get_materials_updated_since.side_effect = RuntimeError(
            'MoySklad unavailable'
        )
        task = ParserTask()

        async_to_sync(task.run)()

        self.assertEqual(task.progress.status, TaskStatus.PARTIAL)
        self.assertIn('материалы', task.progress.message)
        self.assertEqual(task.progress.error, 'MoySklad unavailable')
        # Отметка свежести — только после полной удачи: на неё смотрят
        # и ночной прогон, и страницы.
        self.assertIsNone(cache.get('last_successful_update'))

        entities = {record['entity']: record['status'] for record in task.get_state()['entities']}
        self.assertEqual(entities['materials'], ParserTask.ENTITY_FAILED)
        self.assertEqual(entities['supplies'], ParserTask.ENTITY_OK)

    @patch('sync.sync_task.MoySkladAPIClient')
    @patch('sync.processors.shipments.ShipmentProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.supplies.SupplyProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.purchases.PurchaseOrderProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.processing_plans.ProcessingPlanProcessor.process', new_callable=AsyncMock)
    def test_every_entity_failing_is_still_an_error(
        self,
        processing_plans_process,
        purchase_orders_process,
        supplies_process,
        shipments_process,
        client_class,
    ):
        """Если не обновилось вообще ничего, «частично» было бы враньём."""
        for mock in (processing_plans_process, purchase_orders_process,
                     supplies_process, shipments_process):
            mock.side_effect = RuntimeError('MoySklad unavailable')
        client_class.return_value.get_materials_updated_since.side_effect = RuntimeError(
            'MoySklad unavailable'
        )
        task = ParserTask()

        async_to_sync(task.run)()

        self.assertEqual(task.progress.status, TaskStatus.ERROR)
        self.assertIsNone(cache.get('last_successful_update'))

    @patch('sync.sync_task.MoySkladAPIClient')
    @patch('sync.processors.shipments.ShipmentProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.supplies.SupplyProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.purchases.PurchaseOrderProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.processing_plans.ProcessingPlanProcessor.process', new_callable=AsyncMock)
    def test_entity_timestamps_carry_a_timezone(
        self,
        processing_plans_process,
        purchase_orders_process,
        supplies_process,
        shipments_process,
        client_class,
    ):
        """Отметки уезжают в DateTimeField: наивное время в контейнере (UTC)
        Django истолковал бы как московское — сдвиг на три часа."""
        from django.utils.dateparse import parse_datetime

        client_class.return_value.get_materials_updated_since.return_value = []
        task = ParserTask()

        async_to_sync(task.run)()

        for record in task.get_state()['entities']:
            for field in ('started_at', 'finished_at'):
                moment = parse_datetime(record[field])
                self.assertIsNotNone(moment.tzinfo, f'{record["entity"]}.{field} без зоны')

    @patch('sync.sync_task.MoySkladAPIClient')
    @patch('sync.processors.shipments.ShipmentProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.supplies.SupplyProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.purchases.PurchaseOrderProcessor.process', new_callable=AsyncMock)
    @patch('sync.processors.processing_plans.ProcessingPlanProcessor.process', new_callable=AsyncMock)
    def test_clean_run_marks_freshness(
        self,
        processing_plans_process,
        purchase_orders_process,
        supplies_process,
        shipments_process,
        client_class,
    ):
        client_class.return_value.get_materials_updated_since.return_value = []
        task = ParserTask()

        async_to_sync(task.run)()

        self.assertEqual(task.progress.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(cache.get('last_successful_update'))
        self.assertEqual(
            [record['status'] for record in task.get_state()['entities']],
            [ParserTask.ENTITY_OK] * 5,
        )


class AutoSyncWeeklyCommandTests(TestCase):
    """Ночная команда — тонкая обёртка: сама синхронизация в `sync.runner`,
    одна на кнопку и на расписание."""

    def setUp(self):
        cache.clear()

    def test_command_syncs_last_week_on_schedule(self):
        with patch('sync.management.commands.auto_sync_weekly.runner.execute',
                   return_value=0) as execute:
            call_command('auto_sync_weekly', stdout=StringIO())

        kwargs = execute.call_args.kwargs
        self.assertEqual(kwargs['triggered_by'], 'расписание')
        self.assertTrue(kwargs['auto_sync'])
        self.assertEqual((kwargs['end_date'] - kwargs['start_date']).days, 7)
        # Отметка о свежести данных: по ней страница предупреждает,
        # что автосинхронизация давно не проходила.
        self.assertIsNotNone(cache.get('last_auto_sync_started'))

    def test_failed_sync_fails_the_command_and_does_not_mark_freshness(self):
        with patch('sync.management.commands.auto_sync_weekly.runner.execute',
                   return_value=1):
            with self.assertRaises(CommandError):
                call_command('auto_sync_weekly', stdout=StringIO())

        self.assertIsNone(cache.get('last_auto_sync_started'))

    def test_busy_is_a_skip_and_not_a_failure(self):
        """Очередь синхронизаций хуже пропущенного запуска."""
        output = StringIO()
        with patch('sync.management.commands.auto_sync_weekly.runner.execute',
                   return_value=75):
            call_command('auto_sync_weekly', stdout=output)

        self.assertIn('уже выполняется', output.getvalue())
        self.assertIsNone(cache.get('last_auto_sync_started'))

    def test_dry_run_touches_nothing(self):
        with patch('sync.management.commands.auto_sync_weekly.runner.execute') as execute:
            call_command('auto_sync_weekly', '--dry-run', stdout=StringIO())

        execute.assert_not_called()


class TaskStatusFromDatabaseTests(TestCase):
    """`/parser/task-status/` отвечает по записи в базе, а не по памяти
    процесса: под gunicorn воркеров несколько, и спрашивающий попадает
    не обязательно в тот, где идёт задача."""

    def setUp(self):
        from django.contrib.auth.models import User
        # `/parser/` с 10.09.2026 закрыт суперюзером: синхронизация трогает всю
        # базу и ходит в МойСклад (api/access.py, SUPERUSER_PREFIXES).
        self.user = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        self.client.force_login(self.user)

    def test_no_runs_yet(self):
        response = self.client.get('/parser/task-status/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['is_running'])
        self.assertIsNone(response.json()['state'])

    def test_entity_results_are_visible_to_the_page(self):
        """Страница должна называть сущности, оставшиеся вчерашними, —
        иначе «частично» ничем не отличается от обычной ошибки."""
        from .models import SyncEntityResult

        run = SyncRun.objects.create(status=SyncRun.STATUS_PARTIAL,
                                     message='Обновлено частично, не удались: отгрузки')
        SyncEntityResult.objects.create(run=run, entity='supplies', name='Приёмки',
                                        status=SyncEntityResult.STATUS_OK)
        SyncEntityResult.objects.create(run=run, entity='shipments', name='Отгрузки',
                                        status=SyncEntityResult.STATUS_FAILED,
                                        error='МойСклад недоступен')

        state = self.client.get('/parser/task-status/').json()['state']

        self.assertEqual(state['status'], SyncRun.STATUS_PARTIAL)
        self.assertEqual(
            [(entity['entity'], entity['status']) for entity in state['entities']],
            [('supplies', 'ok'), ('shipments', 'failed')],
        )
        self.assertEqual(state['entities'][1]['error'], 'МойСклад недоступен')

    def test_running_sync_is_visible_to_anyone_who_asks(self):
        """Прогон по расписанию виден и тому, кто его не запускал: состояние
        живёт в базе, а не в памяти процесса."""
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

    def test_entity_results_get_their_own_rows(self):
        """Итог по сущности виден отдельно: по одной строке прогона нельзя
        сказать, что именно осталось вчерашним."""
        run = SyncRun.objects.create()
        heartbeat = self._heartbeat(run, {
            'status': 'partial', 'message': 'Обновлено частично, не удались: отгрузки',
            'processed': 100, 'total': 100, 'error': 'МойСклад недоступен',
            'entities': [
                {'entity': 'supplies', 'name': 'Приёмки', 'status': 'ok', 'error': None,
                 'started_at': '2026-09-07T10:00:00', 'finished_at': '2026-09-07T10:01:00'},
                {'entity': 'shipments', 'name': 'Отгрузки', 'status': 'failed',
                 'error': 'МойСклад недоступен',
                 'started_at': '2026-09-07T10:01:00', 'finished_at': '2026-09-07T10:02:00'},
                # Идущая сущность ещё не итог — её не пишем.
                {'entity': 'materials', 'name': 'Материалы', 'status': None, 'error': None,
                 'started_at': '2026-09-07T10:02:00', 'finished_at': None},
            ],
        })

        heartbeat._mirror_progress(final=True)

        run.refresh_from_db()
        self.assertEqual(run.status, SyncRun.STATUS_PARTIAL)
        self.assertEqual(
            [(row.entity, row.status) for row in run.entities.all()],
            [('supplies', 'ok'), ('shipments', 'failed')],
        )
        self.assertEqual(run.entities.get(entity='shipments').error, 'МойСклад недоступен')

    def test_entity_results_are_written_once(self):
        """Сердцебиение бьётся раз в секунду, а строка на сущность — одна."""
        run = SyncRun.objects.create()
        state = {
            'status': 'running', 'message': 'Отгрузки', 'processed': 80, 'total': 100,
            'error': None,
            'entities': [{'entity': 'supplies', 'name': 'Приёмки', 'status': 'ok',
                          'error': None, 'started_at': '2026-09-07T10:00:00',
                          'finished_at': '2026-09-07T10:01:00'}],
        }
        heartbeat = self._heartbeat(run, state)

        heartbeat._mirror_progress()
        heartbeat._mirror_progress()

        self.assertEqual(run.entities.count(), 1)

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
        self.client.force_login(
            User.objects.create_superuser('admin', 'admin@example.com', 'password'))

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


class SyncRunnerTests(TestCase):
    """Синхронизация порождается отдельным процессом: внутри веб-процесса
    её поток не пережил бы перезапуск воркера под gunicorn."""

    def setUp(self):
        self._logs = tempfile.TemporaryDirectory()
        self.addCleanup(self._logs.cleanup)
        self._settings = override_settings(SCRIPTS_LOGS_DIR=self._logs.name)
        self._settings.enable()
        self.addCleanup(self._settings.disable)

    def test_launch_spawns_the_command_for_the_row_it_created(self):
        from sync import runner

        with patch.object(runner.subprocess, 'Popen', return_value=Mock(pid=1)) as popen:
            run_id = runner.launch(months=12)

        argv = popen.call_args[0][0]
        self.assertIn('sync_data', argv)
        self.assertEqual(argv[argv.index('--run-id') + 1], str(run_id))
        self.assertEqual(argv[argv.index('--months') + 1], '12')
        self.assertEqual(SyncRun.objects.get(pk=run_id).triggered_by, 'кнопка')

    def test_child_output_goes_to_a_file(self):
        """Процесс, умерший до первой отметки в базе, оставляет след только здесь."""
        from sync import runner

        with patch.object(runner.subprocess, 'Popen', return_value=Mock(pid=1)) as popen:
            run_id = runner.launch(months=12)

        log = popen.call_args.kwargs['stdout']
        self.assertEqual(log.name, os.path.join(self._logs.name, f'sync_{run_id}.log'))

    def test_launch_refuses_while_another_sync_is_running(self):
        """Иначе новая строка становится последней, и идущую синхронизацию —
        ночную или чужую — уже нечем ни увидеть, ни остановить."""
        from sync import runner

        SyncRun.objects.create(triggered_by='расписание')

        with patch.object(runner.subprocess, 'Popen') as popen:
            with self.assertRaises(runner.AlreadyRunning):
                runner.launch(months=12)

        popen.assert_not_called()
        self.assertEqual(SyncRun.objects.count(), 1)

    def test_failed_launch_leaves_a_failed_run_and_not_a_hanging_one(self):
        from sync import runner

        with patch.object(runner.subprocess, 'Popen', side_effect=OSError('нет процесса')):
            with self.assertRaises(OSError):
                runner.launch(months=12)

        run = SyncRun.latest()
        self.assertEqual(run.status, SyncRun.STATUS_ERROR)
        self.assertIsNotNone(run.finished_at)
        self.assertFalse(run.is_alive)

    def test_busy_closes_the_row_prepared_by_the_button(self):
        """Иначе карточка на странице висела бы «идёт» до срока годности."""
        from sync import runner
        from .models import SyncLock

        SyncLock.acquire_lock('moysklad_sync', locked_by='кто-то другой')
        run = SyncRun.start(triggered_by='кнопка')

        code = runner.execute(triggered_by='кнопка', months_back=1, run_id=run.id)

        run.refresh_from_db()
        self.assertEqual(code, runner.EXIT_BUSY)
        self.assertFalse(run.is_alive)
        self.assertIsNotNone(run.finished_at)

    def test_execute_attaches_to_the_row_the_button_created(self):
        from sync import runner

        run = SyncRun.start(triggered_by='кнопка')
        task = Mock()
        task.progress.status = TaskStatus.COMPLETED

        with (
            patch.object(runner, 'ParserTask', return_value=task),
            patch.object(runner.asyncio, 'run'),
            patch.object(runner, 'SyncHeartbeat') as heartbeat,
        ):
            code = runner.execute(triggered_by='кнопка', months_back=1, run_id=run.id)

        self.assertEqual(code, runner.EXIT_OK)
        self.assertEqual(heartbeat.call_args.kwargs['run'], run)
        self.assertEqual(SyncRun.objects.count(), 1)

    def test_crash_is_not_erased_by_the_last_heartbeat_snapshot(self):
        """Последний снимок сердцебиения пишет объект из памяти, где статус
        ещё «идёт». Закрой прогон до него — и он вернулся бы в «идёт»
        с пустым finished_at и потерянным текстом ошибки."""
        from sync import runner

        run = SyncRun.start(triggered_by='кнопка')
        task = Mock()
        task.get_state.return_value = {'status': TaskStatus.RUNNING.value, 'message': 'Отгрузки',
                                       'processed': 40, 'total': 100, 'error': None}

        with (
            patch.object(runner, 'ParserTask', return_value=task),
            patch.object(runner.asyncio, 'run', side_effect=RuntimeError('соединение оборвалось')),
        ):
            code = runner.execute(triggered_by='кнопка', months_back=1, run_id=run.id)

        run.refresh_from_db()
        self.assertEqual(code, runner.EXIT_FAILED)
        self.assertEqual(run.status, SyncRun.STATUS_ERROR)
        self.assertIsNotNone(run.finished_at)
        self.assertIn('соединение оборвалось', run.error)
        self.assertFalse(run.is_alive)

    def test_partial_run_has_its_own_exit_code(self):
        """Общая единица делала частичный прогон неотличимым от упавшего:
        в журнале cron обе строки читались как «ОШИБКА»."""
        from sync import runner

        run = SyncRun.start(triggered_by='расписание')
        task = Mock()
        task.progress.status = TaskStatus.PARTIAL
        task.progress.message = 'Обновлено частично, не удались: отгрузки'

        with (
            patch.object(runner, 'ParserTask', return_value=task),
            patch.object(runner.asyncio, 'run'),
            patch.object(runner, 'SyncHeartbeat'),
        ):
            code = runner.execute(triggered_by='расписание', months_back=1, run_id=run.id)

        self.assertEqual(code, runner.EXIT_PARTIAL)
        self.assertNotEqual(runner.EXIT_PARTIAL, runner.EXIT_FAILED)

    def test_broken_start_releases_the_lock(self):
        """Задача ходит за токеном и в кеш ещё до первого запроса. Упади она
        там — блокировка висела бы час, и всё это время пропускались бы
        и ночные прогоны, и нажатия кнопки."""
        from sync import runner
        from .models import SyncLock

        run = SyncRun.start(triggered_by='кнопка')
        with patch.object(runner, 'ParserTask', side_effect=RuntimeError('нет токена')):
            code = runner.execute(triggered_by='кнопка', months_back=1, run_id=run.id)

        self.assertEqual(code, runner.EXIT_FAILED)
        self.assertIsNotNone(SyncLock.acquire_lock('moysklad_sync', locked_by='следующий'))
        run.refresh_from_db()
        self.assertEqual(run.status, SyncRun.STATUS_ERROR)


class SyncDataCommandTests(TestCase):
    def test_half_a_period_is_refused(self):
        """Иначе команда молча синхронизировала бы неделю вместо запрошенного."""
        with self.assertRaisesRegex(CommandError, 'обе даты'):
            call_command('sync_data', '--start-date', '2026-09-01', stdout=StringIO())


class LoadDataViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self._logs = tempfile.TemporaryDirectory()
        self.addCleanup(self._logs.cleanup)
        self._settings = override_settings(SCRIPTS_LOGS_DIR=self._logs.name)
        self._settings.enable()
        self.addCleanup(self._settings.disable)
        self.client.force_login(
            User.objects.create_superuser('admin', 'admin@example.com', 'password'))

    def test_button_gets_a_refusal_while_a_sync_is_running(self):
        SyncRun.objects.create(triggered_by='расписание')

        response = self.client.post('/parser/load-data/', {'months': 12},
                                    content_type='application/json')

        self.assertEqual(response.status_code, 409)
        self.assertIn('уже выполняется', response.json()['message'])

    def test_button_returns_the_number_of_its_run(self):
        from sync import runner

        with patch.object(runner.subprocess, 'Popen', return_value=Mock(pid=1)):
            response = self.client.post('/parser/load-data/', {'months': 12},
                                        content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['run_id'], SyncRun.latest().id)
