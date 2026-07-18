# sync/management/commands/auto_sync_weekly.py
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.core.cache import cache

from sync.models import SyncLock
from sync.sync_task import ParserTask, SyncLockHeartbeat, TaskStatus

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Автоматическая синхронизация данных за последнюю неделю'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет синхронизировано без фактического выполнения'
        )

    def handle(self, *args, **options):
        """Выполняет автоматическую синхронизацию данных за последнюю неделю"""

        logger.info("=" * 60)
        logger.info("AUTO SYNC COMMAND STARTED")
        logger.info(f"Dry run: {options.get('dry_run', False)}")
        logger.info("=" * 60)

        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Будет синхронизирован период {start_date.strftime("%d.%m.%Y")} - {end_date.strftime("%d.%m.%Y")}'
                )
            )
            return

        lock_token = SyncLock.acquire_lock('moysklad_sync', locked_by='auto_sync_weekly')
        if not lock_token:
            message = 'Синхронизация уже выполняется. Пропускаем.'
            self.stdout.write(self.style.WARNING(message))
            logger.warning(message)
            return

        heartbeat = None
        try:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Начало автоматической синхронизации данных за период: {start_date.strftime("%d.%m.%Y")} - {end_date.strftime("%d.%m.%Y")}'
                )
            )

            logger.info(f"Task parameters: start_date={start_date}, end_date={end_date}, auto_sync=True")

            logger.info("Creating and executing auto sync task synchronously...")
            task = ParserTask(
                start_date=start_date,
                end_date=end_date,
                auto_sync=True
            )
            heartbeat = SyncLockHeartbeat(task, 'moysklad_sync', lock_token)
            heartbeat.start()

            import asyncio
            asyncio.run(task.run())

            if task.progress.status != TaskStatus.COMPLETED:
                raise CommandError(
                    task.progress.error
                    or task.progress.message
                    or 'Синхронизация не была завершена'
                )

            success_message = f'Задача автосинхронизации выполнена синхронно'
            self.stdout.write(self.style.SUCCESS(success_message))

            start_time = timezone.now()
            cache.set('last_auto_sync_started', start_time, timeout=None)
            logger.info(f'Auto sync task completed successfully at {start_time}')
            logger.info(f'Period: {start_date.date()} - {end_date.date()}')

        except CommandError:
            logger.exception("Auto sync task completed with an error")
            raise
        except Exception as e:
            error_msg = f'Ошибка при выполнении автосинхронизации: {str(e)}'
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(f'Auto sync error: {str(e)}')
            logger.exception("Full exception traceback:")
            raise CommandError(error_msg) from e

        finally:
            if heartbeat:
                heartbeat.stop()
            SyncLock.release_lock('moysklad_sync', lock_token)
            logger.info("Released auto sync lock")

        completion_msg = 'Автоматическая синхронизация завершена'
        self.stdout.write(self.style.SUCCESS(completion_msg))
        logger.info("=" * 60)
        logger.info("AUTO SYNC COMMAND COMPLETED")
        logger.info("=" * 60)
