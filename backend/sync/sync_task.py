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
from django.utils.dateparse import parse_datetime
from asgiref.sync import sync_to_async

from .logger import logger, structured_logger
from .models import RawMaterial, SyncEntityResult, SyncLock, SyncRun
from .moysklad import MoySkladAPIClient
from .cache import MaterialRegistry, ProductCache
from .utils import get_group_from_pathname


# --- Base Task ---

class TaskStatus(Enum):
    """Статусы выполнения задачи"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    # Часть сущностей обновилась, часть осталась вчерашней. Отдельный статус,
    # а не «ошибка»: разница между «ничего не обновилось» и «обновилось всё,
    # кроме отгрузок» — это разница между «подожди» и «маржа сейчас врёт».
    PARTIAL = "partial"
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

    # Итоги по сущностям. Живут в памяти задачи, а в базу их переносит
    # сердцебиение — из asyncio-цикла обращаться к ORM Django не даёт.
    ENTITY_OK = 'ok'
    ENTITY_FAILED = 'failed'
    ENTITY_STOPPED = 'stopped'

    def __init__(self):
        self._progress = TaskProgress(
            status=TaskStatus.IDLE,
            message="Задача создана"
        )
        self._stop_requested = False
        self._entities = []

    def entity_started(self, entity: str, name: str) -> None:
        # timezone.now(), а не datetime.now(): отметки уезжают в DateTimeField
        # при USE_TZ, и наивное время в контейнере (UTC) Django истолковал бы
        # как московское — все отметки сдвинулись бы на три часа.
        self._entities.append({
            'entity': entity, 'name': name, 'status': None, 'error': None,
            'started_at': timezone.now().isoformat(), 'finished_at': None,
        })

    def entity_finished(self, entity: str, status: str, error: str = None) -> None:
        for record in reversed(self._entities):
            if record['entity'] == entity:
                record['status'] = status
                record['error'] = error
                record['finished_at'] = timezone.now().isoformat()
                return

    @property
    def failed_entities(self) -> list:
        return [record for record in self._entities if record['status'] == self.ENTITY_FAILED]

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
            elif kwargs.get('status') in [TaskStatus.COMPLETED, TaskStatus.PARTIAL,
                                         TaskStatus.ERROR, TaskStatus.STOPPED]:
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
            'error': self._progress.error,
            'entities': [dict(record) for record in self._entities],
        }


class SyncHeartbeat:
    """Пока задача жива, отмечается за неё в базе — и делает это дважды.

    Продлевает lease блокировки, иначе долгий прогон сочтут брошенным.
    И переносит прогресс в `SyncRun`: состояние задачи живёт в памяти
    процесса, а спрашивают его по HTTP — под gunicorn это разные процессы,
    и в память задачи спрашивающий не попадает вовсе. Ночной прогон вообще
    идёт отдельной командой, и без записи в базу интерфейс о нём не знает.

    Почему отсюда, а не из самой задачи: задача крутится в цикле asyncio,
    а обращаться к ORM из async-кода Django запрещает.
    """

    # Шаг сердцебиения. Прогресс переносим на каждом, блокировку продлеваем
    # раз в `interval_seconds` — она этого чаще не просит.
    TICK_SECONDS = 1.0

    # Отмечаемся в базе, даже когда состояние не менялось: по свежести записи
    # видно, что прогон жив, а не брошен (см. SyncRun.STALE_AFTER_SECONDS).
    TOUCH_SECONDS = 5.0

    def __init__(self, task: BaseTask, lock_type: str, lock_token: str, run=None):
        self.task = task
        self.lock_type = lock_type
        self.lock_token = lock_token
        self.run = run
        self.interval_seconds = getattr(settings, 'SYNC_LOCK_HEARTBEAT_SECONDS', 300)
        self._stop_event = threading.Event()
        self._thread = None
        self._last_mirror = None
        self._last_touch = 0.0
        self._mirrored_entities = set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        close_old_connections()
        try:
            # Шаг не крупнее интервала продления: иначе настройка
            # SYNC_LOCK_HEARTBEAT_SECONDS меньше секунды просто не работала бы.
            tick = min(self.TICK_SECONDS, self.interval_seconds)
            since_lock = 0.0
            while not self._stop_event.wait(tick):
                self._mirror_progress()
                self._check_stop_request()

                since_lock += tick
                if since_lock < self.interval_seconds:
                    continue
                since_lock = 0.0
                if not SyncLock.refresh_lock(self.lock_type, self.lock_token):
                    structured_logger.error(
                        "Потеряна блокировка синхронизации; задача будет остановлена"
                    )
                    self.task.stop()
                    return
        finally:
            close_old_connections()

    # Статусы, при которых прогон считается законченным.
    FINAL_STATUSES = (
        SyncRun.STATUS_COMPLETED, SyncRun.STATUS_PARTIAL,
        SyncRun.STATUS_ERROR, SyncRun.STATUS_STOPPED,
    )

    def _mirror_progress(self, final: bool = False) -> None:
        """Переносит состояние задачи в строку прогона."""
        if not self.run:
            return
        try:
            state = self.task.get_state()
            status = state.get('status')

            # Итоги по сущностям переносим до проверки «состояние не менялось»:
            # сущность могла кончиться, не сдвинув ни процент, ни сообщение.
            self._mirror_entities(state.get('entities') or [])

            # Первый удар сердца может прийтись на момент, когда задача ещё
            # только создана: у неё статус `idle`, которого у прогона нет.
            # Записать его значило бы объявить прогон законченным — и это
            # уже не исправить, отметку о завершении мы ставим один раз.
            if status == TaskStatus.IDLE.value:
                return

            snapshot = (status, state.get('message'), state.get('processed'))
            elapsed = time.time() - self._last_touch
            if not final and snapshot == self._last_mirror and elapsed < self.TOUCH_SECONDS:
                return

            self.run.status = status if status in self.FINAL_STATUSES else SyncRun.STATUS_RUNNING
            self.run.message = (state.get('message') or '')[:255]
            self.run.processed = max(0, min(100, int(state.get('processed') or 0)))
            self.run.total = max(1, min(100, int(state.get('total') or 100)))
            self.run.error = state.get('error') or ''
            if self.run.status in self.FINAL_STATUSES and not self.run.finished_at:
                self.run.finished_at = timezone.now()
            self.run.save(update_fields=[
                'status', 'message', 'processed', 'total', 'error',
                'finished_at', 'updated_at',
            ])
            self._last_mirror = snapshot
            self._last_touch = time.time()
        except Exception:
            # Прогон важнее его отображения: не смогли записать — не мешаем.
            # Соединение после сбоя закрываем: Django помечает его негодным,
            # и без этого молчали бы уже все последующие удары сердца, а прогон
            # через минуту стал бы выглядеть брошенным.
            logger.exception('Не удалось записать состояние прогона синхронизации')
            try:
                close_old_connections()
            except Exception:
                pass

    def _mirror_entities(self, entities) -> None:
        """Переносит итоги по сущностям в `SyncEntityResult`.

        Пишем только законченные и только изменившиеся: строка на сущность
        за прогон, а сердцебиение бьётся раз в секунду.
        """
        if not self.run or not entities:
            return
        for record in entities:
            status = record.get('status')
            if not status:
                continue
            key = (record['entity'], status)
            if key in self._mirrored_entities:
                continue
            SyncEntityResult.objects.update_or_create(
                run=self.run, entity=record['entity'],
                defaults={
                    'name': record['name'],
                    'status': status,
                    'error': (record.get('error') or '')[:2000],
                    'started_at': parse_datetime(record['started_at']) if record.get('started_at') else None,
                    'finished_at': parse_datetime(record['finished_at']) if record.get('finished_at') else None,
                },
            )
            self._mirrored_entities.add(key)

    def _check_stop_request(self) -> None:
        """Остановку просят через базу: нажавший «Стоп» сидит в другом процессе.

        Через память это работало, только пока сервер был одним процессом
        и синхронизацию запускала кнопка. Прогон по расписанию идёт вообще
        отдельной командой, и остановить его было нечем.
        """
        if not self.run:
            return
        try:
            if SyncRun.objects.filter(pk=self.run.pk, stop_requested=True).exists():
                structured_logger.info('Получена просьба остановить синхронизацию')
                self.task.stop()
        except Exception:
            logger.exception('Не удалось проверить просьбу об остановке')

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        # Последний снимок: без него прогон навсегда остался бы «идёт»,
        # пока не протухнет по сроку.
        self._mirror_progress(final=True)


# Прежнее имя: он продлевал только блокировку.
SyncLockHeartbeat = SyncHeartbeat


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

    async def _sync_entity(self, entity: str, name: str, work) -> bool:
        """Провести одну сущность и запомнить, чем она кончилась.

        Падение одной сущности больше не отменяет остальные: приёмки
        не виноваты в том, что МойСклад ответил 429 на отгрузках, а их
        свежие данные нужны сегодня, а не после починки отгрузок. Прогон
        при этом закончится «частично» — смесь свежего и вчерашнего должна
        быть видна, а не выглядеть удачей.
        """
        self.entity_started(entity, name)
        try:
            await work()
        except Exception as e:
            structured_logger.error(f"{name}: не обновлены — {e}")
            logger.exception("Ошибка синхронизации: %s", name)
            self.entity_finished(entity, self.ENTITY_FAILED, str(e))
            return False

        if self.should_stop():
            self.entity_finished(entity, self.ENTITY_STOPPED)
            return False

        self.entity_finished(entity, self.ENTITY_OK)
        return True

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

            ok = await self._sync_entity(
                'processing_plans', 'Техкарты',
                lambda: ProcessingPlanProcessor(self.client, self.product_cache, self).process(),
            )
            if self.should_stop():
                return

            self._update_stage_progress(
                1, 1.0,
                "Загрузка техкарт завершена" if ok else "Техкарты не обновлены",
                "Техкарты загружены успешно" if ok else "Идём дальше: остальные сущности не виноваты",
            )

            # Этап 2: Синхронизация материалов (20% - 40%)
            self._update_stage_progress(2, 0.0, "Синхронизация материалов", "Подготовка к синхронизации")

            ok = await self._sync_entity('materials', 'Материалы', self.sync_materials)
            if self.should_stop():
                return

            self._update_stage_progress(
                2, 1.0,
                "Синхронизация материалов завершена" if ok else "Материалы не обновлены",
                "Материалы синхронизированы" if ok else "Идём дальше",
            )

            # Этап 3: Обработка заказов поставщиков (40% - 60%)
            time_ranges = self._get_time_ranges()
            self._update_stage_progress(3, 0.0, "Загрузка заказов поставщикам", "Подготовка к загрузке заказов")

            ok = await self._sync_entity(
                'purchase_orders', 'Заказы поставщикам',
                lambda: PurchaseOrderProcessor(self.client, self.product_cache, self).process(time_ranges),
            )
            if self.should_stop():
                return

            self._update_stage_progress(
                3, 1.0,
                "Загрузка заказов завершена" if ok else "Заказы поставщикам не обновлены",
                "Заказы поставщикам загружены" if ok else "Идём дальше",
            )

            # Этап 4: Обработка приемок (60% - 80%)
            self._update_stage_progress(4, 0.0, "Загрузка приемок", "Подготовка к загрузке приемок")

            ok = await self._sync_entity(
                'supplies', 'Приёмки',
                lambda: SupplyProcessor(self.client, self.product_cache, self).process(time_ranges),
            )
            if self.should_stop():
                return

            self._update_stage_progress(
                4, 1.0,
                "Загрузка приемок завершена" if ok else "Приёмки не обновлены",
                "Приемки загружены" if ok else "Идём дальше",
            )

            # Этап 5: Обработка отгрузок (80% - 100%)
            self._update_stage_progress(5, 0.0, "Загрузка отгрузок", "Подготовка к загрузке отгрузок")

            await self._sync_entity(
                'shipments', 'Отгрузки',
                lambda: ShipmentProcessor(
                    self.client, self.product_cache, self.material_registry, self,
                ).process(time_ranges),
            )

            if not self.should_stop():
                self._finish()

        except Exception as e:
            structured_logger.error(f"Критическая ошибка при выполнении задачи: {str(e)}")
            logger.exception("Error in parser task execution")
            self.update_progress(
                status=TaskStatus.ERROR,
                message="Ошибка при выполнении задачи",
                error=str(e)
            )

    def _finish(self):
        """Итог прогона: удача, «частично» или ошибка.

        Отметку свежести (`last_successful_update`) ставим только после
        полной удачи: на неё смотрит и ночной прогон, и страницы — сказать
        «данные свежие», когда отгрузки остались вчерашними, значит соврать
        ровно там, где это никто не проверит.
        """
        failed = self.failed_entities
        names = ', '.join(record['name'].lower() for record in failed)
        # Остановленные в знаменатель не берём: прогон, где всё упало, а
        # последнюю сущность успели остановить, — это не «частично».
        attempted = [record for record in self._entities
                     if record['status'] != self.ENTITY_STOPPED]

        if failed and len(failed) == len(attempted):
            structured_logger.error("Ни одна сущность не обновилась")
            self.update_progress(
                status=TaskStatus.ERROR,
                message="Синхронизация не удалась",
                processed=100,
                total=100,
                details=f"Не обновились: {names}",
                error=failed[0]['error'],
            )
            return

        if failed:
            structured_logger.error(f"Обновлено частично, не удались: {names}")
            self.update_progress(
                status=TaskStatus.PARTIAL,
                message=f"Обновлено частично, не удались: {names}",
                processed=100,
                total=100,
                details="Остальные сущности обновлены",
                error=failed[0]['error'],
            )
            return

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

        if getattr(self, 'is_auto_sync', False):
            cache.set('last_auto_sync_update', update_time, timeout=None)
        else:
            cache.set('last_manual_update', update_time, timeout=None)
