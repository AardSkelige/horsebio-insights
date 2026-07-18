# sync/sync_task.py
# Merged from parser/tasks/base.py + parser/tasks/manager.py + parser/tasks/parser/parser_task.py

import asyncio
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Type
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections
from django.utils import timezone
from asgiref.sync import sync_to_async

from .logger import logger, structured_logger
from .models import RawMaterial, SyncLock
from .moysklad import MoySkladAPIClient
from .cache import MaterialRegistry, ProductCache
from .utils import get_group_from_pathname


# --- Base Task ---

class TaskStatus(Enum):
    """Статусы выполнения задачи"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class TaskProgress:
    """Информация о прогрессе задачи"""
    status: TaskStatus
    message: str
    details: Optional[str] = None
    processed: int = 0
    total: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class BaseTask(ABC):
    """Базовый класс для всех задач"""

    def __init__(self):
        self._progress = TaskProgress(
            status=TaskStatus.IDLE,
            message="Задача создана"
        )
        self._stop_requested = False

    @property
    def progress(self) -> TaskProgress:
        return self._progress

    @abstractmethod
    async def run(self) -> None:
        pass

    def stop(self) -> None:
        self._stop_requested = True
        self._progress.status = TaskStatus.STOPPED
        self._progress.message = "Задача остановлена пользователем"
        self._progress.completed_at = datetime.now()

    def should_stop(self) -> bool:
        return self._stop_requested

    def update_progress(self, **kwargs) -> None:
        """Обновление прогресса с предотвращением дублирования"""
        should_update = False

        for key, value in kwargs.items():
            if hasattr(self._progress, key):
                current_value = getattr(self._progress, key)
                if current_value != value:
                    setattr(self._progress, key, value)
                    should_update = True

        if should_update:
            if kwargs.get('status') == TaskStatus.RUNNING and not self._progress.started_at:
                self._progress.started_at = datetime.now()
            elif kwargs.get('status') in [TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.STOPPED]:
                self._progress.completed_at = datetime.now()

    def get_state(self) -> dict:
        return {
            'status': self._progress.status.value,
            'message': self._progress.message,
            'details': self._progress.details,
            'processed': self._progress.processed,
            'total': self._progress.total,
            'started_at': self._progress.started_at.isoformat() if self._progress.started_at else None,
            'completed_at': self._progress.completed_at.isoformat() if self._progress.completed_at else None,
            'error': self._progress.error
        }


class SyncLockHeartbeat:
    """Поддерживает lease блокировки, пока задача выполняется."""

    def __init__(self, task: BaseTask, lock_type: str, lock_token: str):
        self.task = task
        self.lock_type = lock_type
        self.lock_token = lock_token
        self.interval_seconds = getattr(settings, 'SYNC_LOCK_HEARTBEAT_SECONDS', 300)
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        close_old_connections()
        try:
            while not self._stop_event.wait(self.interval_seconds):
                if not SyncLock.refresh_lock(self.lock_type, self.lock_token):
                    structured_logger.error(
                        "Потеряна блокировка синхронизации; задача будет остановлена"
                    )
                    self.task.stop()
                    return
        finally:
            close_old_connections()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)


# --- Task Manager ---

class TaskManager:
    """Менеджер задач - синглтон для управления асинхронными задачами"""
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Инициализация начального состояния"""
        self._current_task = None
        self._task_future = None
        self._loop = None
        self._thread = None
        self._is_running = False
        self._event = threading.Event()
        self._cleanup_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._cached_state = None
        self._last_state_update = 0

    def _cleanup(self, preserve_terminal_state: bool = True) -> None:
        """Очистка ресурсов после того, как loop задачи уже завершил работу."""
        # Serialize cleanup with start/stop so a new task cannot be installed
        # while the old worker is clearing its resources.
        with self._lock, self._cleanup_lock:
            if preserve_terminal_state and self._current_task:
                state = self._current_task.get_state()
                if state.get('status') in {
                    TaskStatus.COMPLETED.value,
                    TaskStatus.ERROR.value,
                    TaskStatus.STOPPED.value,
                }:
                    with self._state_lock:
                        self._cached_state = state
                        self._last_state_update = time.time()

            self._is_running = False

            if self._loop and not self._loop.is_closed():
                try:
                    # _cleanup is normally called by run_loop after
                    # run_until_complete has returned. Never drive or cancel an
                    # event loop from the HTTP/SSE thread.
                    if not self._loop.is_running():
                        self._loop.close()
                except Exception:
                    logger.exception("Error closing task event loop")
                finally:
                    self._loop = None

            self._current_task = None
            self._thread = None
            self._event.clear()
            if not preserve_terminal_state:
                with self._state_lock:
                    self._cached_state = None
                    self._last_state_update = 0

    async def _run_task(self, task: BaseTask) -> None:
        """Выполнение задачи с обработкой исключений"""
        try:
            structured_logger.info("Начало выполнения задачи")
            await task.run()
            if task.progress.status == TaskStatus.ERROR:
                structured_logger.error("Задача завершена с ошибкой")
            elif task.progress.status == TaskStatus.STOPPED:
                structured_logger.warning("Задача была остановлена")
            else:
                structured_logger.success("Задача завершена успешно")
        except asyncio.CancelledError:
            if task.progress.status != TaskStatus.STOPPED:
                task.stop()
            raise
        except Exception as e:
            logger.exception("Ошибка выполнения задачи")
            task.update_progress(
                status=TaskStatus.ERROR,
                message="Ошибка при выполнении задачи",
                error=str(e),
            )
        finally:
            self._event.set()

    def start_task(self, task_class: Type[BaseTask], **kwargs) -> Dict:
        """Запуск новой задачи с проверкой текущего состояния и блокировкой БД"""
        with self._lock:
            if self._is_running:
                if not self._thread or not self._thread.is_alive():
                    logger.warning("Dead thread detected, forcing cleanup")
                    self._cleanup()
                else:
                    return {
                        'status': 'error',
                        'message': 'Другая задача уже выполняется'
                    }

            lock_token = SyncLock.acquire_lock('moysklad_sync', locked_by='task_manager_ui')
            if not lock_token:
                return {
                    'status': 'error',
                    'message': 'Синхронизация уже выполняется (другой процесс)'
                }

            try:
                with self._state_lock:
                    self._cached_state = None
                    self._last_state_update = 0

                def run_loop():
                    heartbeat = None
                    try:
                        heartbeat = SyncLockHeartbeat(
                            self._current_task,
                            'moysklad_sync',
                            lock_token,
                        )
                        heartbeat.start()
                        self._loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(self._loop)
                        try:
                            self._loop.run_until_complete(self._run_task(self._current_task))
                        except asyncio.CancelledError:
                            return
                    except Exception as e:
                        logger.error(f"Error in event loop: {e}")
                        if self._current_task:
                            self._current_task.update_progress(
                                status=TaskStatus.ERROR,
                                message="Ошибка запуска задачи",
                                error=str(e),
                            )
                    finally:
                        if heartbeat:
                            heartbeat.stop()
                        self._cleanup()
                        try:
                            SyncLock.release_lock('moysklad_sync', lock_token)
                        except Exception:
                            pass

                self._current_task = task_class(**kwargs)
                structured_logger.info(f"Создана новая задача: {task_class.__name__}")

                self._thread = threading.Thread(target=run_loop)
                self._thread.daemon = True
                self._is_running = True
                self._thread.start()

                return {
                    'status': 'started',
                    'message': 'Задача успешно запущена'
                }
            except Exception as e:
                logger.exception("Ошибка запуска задачи")
                self._cleanup(preserve_terminal_state=False)
                try:
                    SyncLock.release_lock('moysklad_sync', lock_token)
                except Exception:
                    pass
                return {
                    'status': 'error',
                    'message': f'Ошибка при запуске задачи: {str(e)}'
                }

    def stop_current_task(self) -> Dict:
        """Запрос кооперативной остановки; ресурсы закроет поток задачи."""
        with self._lock:
            if not self._is_running or not self._current_task:
                return {
                    'status': 'error',
                    'message': 'Нет активной задачи'
                }

            try:
                self._current_task.stop()

                return {
                    'status': 'success',
                    'message': 'Задача остановлена'
                }
            except Exception as e:
                logger.exception("Ошибка остановки задачи")
                return {
                    'status': 'error',
                    'message': f'Ошибка при остановке задачи: {str(e)}'
                }

    def get_current_state(self) -> Optional[Dict]:
        """Получение текущего состояния задачи"""
        with self._state_lock:
            current_time = time.time()

            if not self._is_running or not self._current_task:
                return self._cached_state.copy() if self._cached_state else None

            try:
                if (not self._cached_state or
                    current_time - self._last_state_update >= 0.1):
                    self._cached_state = self._current_task.get_state()
                    self._last_state_update = current_time
                    logger.debug(f"Updated cached state: {self._cached_state}")
                return self._cached_state.copy()
            except Exception as e:
                logger.error(f"Error getting task state: {e}")
                return None

    def is_task_running(self) -> bool:
        """Проверка выполнения задачи"""
        return self._is_running and self._current_task is not None and \
               self._thread and self._thread.is_alive()

    def cleanup_state(self):
        """Удаляет уже прочитанное terminal state, не вмешиваясь в loop."""
        with self._state_lock:
            if not self._is_running:
                self._cached_state = None
                self._last_state_update = 0

    def force_reset(self):
        """Принудительный сброс всех состояний менеджера"""
        with self._lock:
            if self._is_running and self._current_task:
                self._current_task.stop()
                return
            self._cleanup(preserve_terminal_state=False)


# --- Parser Task ---

class ParserTask(BaseTask):
    """Задача для парсинга данных из МойСклад"""

    def __init__(self, months_back: int = 12, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, auto_sync: bool = False):
        super().__init__()
        self.months_back = months_back
        self.start_date = start_date
        self.end_date = end_date
        self.is_auto_sync = auto_sync
        self.client = MoySkladAPIClient(settings.MOYSKLAD_TOKEN)
        self.product_cache = ProductCache()
        self.material_registry = MaterialRegistry()

    def _update_stage_progress(self, stage: int, stage_progress: float, message: str, details: str = None):
        """Обновляет прогресс внутри этапа"""
        total_stages = 5
        stage_weight = 1.0 / total_stages
        base_progress = (stage - 1) * stage_weight
        current_stage_progress = stage_progress * stage_weight
        total_progress = base_progress + current_stage_progress
        processed = int(total_progress * 100)
        total = 100

        self.update_progress(
            message=message,
            details=details,
            processed=processed,
            total=total
        )

    def _get_time_ranges(self) -> List[Tuple[datetime, datetime]]:
        """Получение списка временных периодов для загрузки"""
        if self.start_date and self.end_date:
            ranges = []
            current_date = self.start_date

            while current_date < self.end_date:
                if current_date.month == 12:
                    next_month = current_date.replace(year=current_date.year + 1, month=1, day=1)
                else:
                    next_month = current_date.replace(month=current_date.month + 1, day=1)

                range_end = min(next_month, self.end_date)
                ranges.append((current_date, range_end))
                current_date = next_month

            structured_logger.info(f"Сгенерировано {len(ranges)} временных диапазонов для периода {self.start_date} - {self.end_date}")
            for i, (start, end) in enumerate(ranges, 1):
                structured_logger.info(f"Диапазон {i}: {start.strftime('%Y-%m-%d')} - {end.strftime('%Y-%m-%d')}", indent=1)

            return ranges

        current_date = timezone.now()
        ranges = []

        for i in range(self.months_back):
            end_date = current_date - relativedelta(months=i)
            start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if i == 0:
                ranges.append((start_date, end_date))
            else:
                end_date = start_date + relativedelta(months=1) - timedelta(seconds=1)
                ranges.append((start_date, end_date))

        return ranges

    async def sync_materials(self):
        """Инкрементальная синхронизация материалов"""
        structured_logger.section_start("Синхронизация материалов", "Инкрементальное обновление материалов из МойСклад")
        try:
            last_sync_time = cache.get('last_materials_sync_time')

            if not last_sync_time:
                last_sync_time = timezone.now() - timedelta(days=7)

            self.update_progress(
                status=TaskStatus.RUNNING,
                message="Начало синхронизации материалов",
                details=f"Проверка материалов, обновленных после {last_sync_time.strftime('%Y-%m-%d %H:%M')}"
            )

            updated_materials = self.client.get_materials_updated_since(last_sync_time)

            structured_logger.info(f"Получено {len(updated_materials)} обновленных материалов из МойСклад")

            total_materials = len(updated_materials)
            self.update_progress(
                message=f"Найдено {total_materials} обновленных материалов в МойСклад",
                details=f"Проверка {total_materials} материалов на обновления"
            )

            updated_count = 0
            for idx, material_data in enumerate(updated_materials, 1):
                if self.should_stop():
                    return

                material_id = material_data.get('id')
                if not material_id:
                    continue

                if idx % 5 == 0 or idx == total_materials:
                    progress_within_stage = idx / total_materials if total_materials > 0 else 1.0
                    self._update_stage_progress(
                        2,
                        progress_within_stage,
                        f"Синхронизация материалов ({idx}/{total_materials})",
                        f"Обработка: {material_data.get('name', 'Неизвестный материал')}"
                    )

                @sync_to_async(thread_sensitive=True)
                def get_material_from_db():
                    return RawMaterial.objects.filter(external_id=material_id).first()

                material = await get_material_from_db()
                path_name = material_data.get('pathName', '')

                group = get_group_from_pathname(path_name)

                if material:
                    if group and material.group != group:
                        @sync_to_async(thread_sensitive=True)
                        def update_material():
                            material.group = group
                            material.save()
                            return True

                        updated = await update_material()
                        if updated:
                            updated_count += 1
                            structured_logger.success(f"Обновлена группа материала {material.name}: {material.group} → {group}", indent=2)
                    else:
                        structured_logger.info(f"Материал {material.name} не требует обновления", indent=2)
                else:
                    structured_logger.info(f"Новый материал: {material_data.get('name')}", indent=2)

                await asyncio.sleep(0.1)

            cache.set('last_materials_sync_time', timezone.now(), timeout=None)

            self.update_progress(
                message=f"Синхронизация материалов завершена. Обновлено: {updated_count}/{total_materials}",
                details=f"Обработано всего: {total_materials} материалов"
            )

            stats = {
                "Всего материалов": total_materials,
                "Обновлено": updated_count,
                "Пропущено": total_materials - updated_count
            }
            structured_logger.stats("Результат синхронизации материалов", stats)

        except Exception as e:
            structured_logger.error(f"Ошибка при синхронизации материалов: {str(e)}")
            logger.exception("Error in sync_materials")
            self.update_progress(
                status=TaskStatus.ERROR,
                message="Ошибка при синхронизации материалов",
                error=str(e)
            )
            raise
        finally:
            structured_logger.section_end("Синхронизация материалов")

    async def run(self):
        """Основной метод выполнения задачи"""
        # Import processors here to avoid circular imports
        from .processors.processing_plans import ProcessingPlanProcessor
        from .processors.shipments import ShipmentProcessor
        from .processors.supplies import SupplyProcessor
        from .processors.purchases import PurchaseOrderProcessor

        task_type = 'AUTO SYNC' if getattr(self, 'is_auto_sync', False) else 'MANUAL'
        description = f"Тип: {task_type} | Период: {self.start_date} - {self.end_date} | Месяцев назад: {self.months_back}"

        structured_logger.section_start("Парсер задач", description)
        try:
            self.update_progress(
                status=TaskStatus.RUNNING,
                message="Запуск обработки данных",
                processed=0,
                total=100,
                details="Инициализация задачи"
            )

            # Этап 1: Обработка техкарт (0% - 20%)
            self._update_stage_progress(1, 0.0, "Загрузка техкарт", "Подготовка к загрузке техкарт производства")

            processor = ProcessingPlanProcessor(self.client, self.product_cache, self)
            await processor.process()
            if self.should_stop():
                return

            self._update_stage_progress(1, 1.0, "Загрузка техкарт завершена", "Техкарты загружены успешно")

            # Этап 2: Синхронизация материалов (20% - 40%)
            self._update_stage_progress(2, 0.0, "Синхронизация материалов", "Подготовка к синхронизации")

            await self.sync_materials()
            if self.should_stop():
                return

            self._update_stage_progress(2, 1.0, "Синхронизация материалов завершена", "Материалы синхронизированы")

            # Этап 3: Обработка заказов поставщиков (40% - 60%)
            time_ranges = self._get_time_ranges()
            self._update_stage_progress(3, 0.0, "Загрузка заказов поставщикам", "Подготовка к загрузке заказов")

            purchase_processor = PurchaseOrderProcessor(self.client, self.product_cache, self)
            await purchase_processor.process(time_ranges)
            if self.should_stop():
                return

            self._update_stage_progress(3, 1.0, "Загрузка заказов завершена", "Заказы поставщикам загружены")

            # Этап 4: Обработка приемок (60% - 80%)
            self._update_stage_progress(4, 0.0, "Загрузка приемок", "Подготовка к загрузке приемок")

            supply_processor = SupplyProcessor(self.client, self.product_cache, self)
            await supply_processor.process(time_ranges)
            if self.should_stop():
                return

            self._update_stage_progress(4, 1.0, "Загрузка приемок завершена", "Приемки загружены")

            # Этап 5: Обработка отгрузок (80% - 100%)
            self._update_stage_progress(5, 0.0, "Загрузка отгрузок", "Подготовка к загрузке отгрузок")

            shipment_processor = ShipmentProcessor(
                self.client,
                self.product_cache,
                self.material_registry,
                self
            )
            await shipment_processor.process(time_ranges)

            if not self.should_stop():
                structured_logger.section_end("Парсер задач", "Все компоненты обработаны успешно")
                self.update_progress(
                    status=TaskStatus.COMPLETED,
                    message="Задача успешно завершена",
                    processed=100,
                    total=100,
                    details="Все этапы обработки завершены"
                )
                update_time = timezone.now()

                cache.set('last_successful_update', update_time, timeout=None)

                is_auto = hasattr(self, 'is_auto_sync') and self.is_auto_sync

                if is_auto:
                    cache.set('last_auto_sync_update', update_time, timeout=None)
                else:
                    cache.set('last_manual_update', update_time, timeout=None)

        except Exception as e:
            structured_logger.error(f"Критическая ошибка при выполнении задачи: {str(e)}")
            logger.exception("Error in parser task execution")
            self.update_progress(
                status=TaskStatus.ERROR,
                message="Ошибка при выполнении задачи",
                error=str(e)
            )
