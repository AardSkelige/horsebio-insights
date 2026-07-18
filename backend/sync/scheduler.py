# sync/scheduler.py
import threading
import schedule
import time
import logging
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from .logger import structured_logger

logger = logging.getLogger(__name__)

class AutoSyncScheduler:
    """Планировщик автосинхронизации, интегрированный в Django"""

    _started = False  # Класс-переменная для защиты от двойного запуска

    def __init__(self):
        self.running = False
        self.thread = None

    def start(self):
        """Запускает планировщик в отдельном потоке"""
        if self.running or AutoSyncScheduler._started:
            return

        AutoSyncScheduler._started = True

        # Только в продакшене
        if getattr(settings, 'DEBUG', True):
            structured_logger.info("Планировщик отключен в режиме отладки")
            return

        self.running = True

        schedule.every().day.at("09:00").do(self._run_inventory_check)
        schedule.every().day.at("11:00").do(self._run_auto_sync)

        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.thread.start()

        structured_logger.success("Планировщик запущен: инвентаризация в 09:00, синхронизация в 11:00")

    def _scheduler_loop(self):
        """Основной цикл планировщика"""
        while self.running:
            schedule.run_pending()
            time.sleep(60)

    def _run_auto_sync(self):
        """Выполняет автосинхронизацию"""

        structured_logger.section_start(
            "Запланированная автосинхронизация",
            f"Время: {timezone.now().strftime('%d.%m.%Y %H:%M')}"
        )

        try:
            from sync.sync_task import ParserTask, SyncLockHeartbeat, TaskStatus
            from sync.models import SyncLock

            lock_token = SyncLock.acquire_lock('moysklad_sync', locked_by='auto_scheduler')
            if not lock_token:
                structured_logger.warning("Синхронизация уже выполняется, пропускаем")
                return

            heartbeat = None
            try:
                end_date = timezone.now()
                start_date = end_date - timedelta(days=7)

                structured_logger.info(f"Период синхронизации: {start_date.date()} - {end_date.date()}")

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
                    raise RuntimeError(
                        task.progress.error
                        or task.progress.message
                        or 'Синхронизация не была завершена'
                    )

                structured_logger.section_end("Запланированная автосинхронизация", "Выполнена успешно")

            finally:
                if heartbeat:
                    heartbeat.stop()
                SyncLock.release_lock('moysklad_sync', lock_token)

        except Exception as e:
            structured_logger.error(f"Ошибка запланированной автосинхронизации: {str(e)}")
            logger.exception("Auto sync error:")

    def _run_inventory_check(self):
        """Ежедневная проверка инвентаризации в 09:00"""
        structured_logger.section_start(
            "Проверка инвентаризации",
            f"Время: {timezone.now().strftime('%d.%m.%Y %H:%M')}"
        )
        try:
            from inventory_tracking.services.inventory_checker import InventoryChecker
            run = InventoryChecker().run(triggered_by='scheduler')
            structured_logger.section_end(
                "Проверка инвентаризации",
                f"Завершена: {run.inventoried_count}/{run.total_products} позиций проинвентаризовано"
            )
        except Exception as e:
            structured_logger.error(f"Ошибка проверки инвентаризации: {str(e)}")
            logger.exception("Inventory check error:")

# Глобальный экземпляр планировщика
scheduler = AutoSyncScheduler()
