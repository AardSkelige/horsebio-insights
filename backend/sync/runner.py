# sync/runner.py
"""
Запуск синхронизации — единственное место, где она порождается.

Кнопка «Обновить» и расписание делают одно и то же: порождают процесс
`manage.py sync_data`. В веб-процессе не остаётся ничего — ни потока,
ни состояния.

Так сделано не ради единообразия. Раньше кнопка запускала поток внутри
Django и сразу отвечала браузеру, а поток работал минутами. Под `runserver`
это держалось на том, что процесс один и живёт сутками. Gunicorn
перезапускает воркер по счётчику запросов и не ждёт фоновых потоков —
синхронизация оборвалась бы на середине, молча, посреди записи документов.

Состояние прогона живёт в `SyncRun` (см. `SyncHeartbeat`), поэтому
порождающему процессу и не нужно ничего помнить.
"""
import asyncio
import glob
import logging
import os
import subprocess
import sys

from django.conf import settings
from django.utils import timezone

from .models import SyncLock, SyncRun
from .sync_task import ParserTask, SyncHeartbeat, TaskStatus

logger = logging.getLogger(__name__)

# Коды выхода команды. Те же, что у проверок: пропуск отделён от ошибки,
# иначе «уже идёт» неотличимо от «упало».
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_BUSY = 75


class AlreadyRunning(Exception):
    """Синхронизация уже идёт — в этом процессе или в любом другом."""


def launch(start_date=None, end_date=None, months=None):
    """Порождает `manage.py sync_data` и сразу возвращает номер прогона.

    Номер нужен странице немедленно: без него первый же опрос состояния
    находит прошлый прогон — законченный — и гасит полосу.
    """
    # Проверяем занятость до того, как завести прогон. Иначе строка нового
    # прогона становится последней, страница показывает по ней «не идёт»,
    # а идущую синхронизацию — чужую или ночную — уже нечем ни увидеть,
    # ни остановить: и статус, и «Стоп» смотрят на последний прогон.
    current = SyncRun.latest()
    if current and current.is_alive:
        raise AlreadyRunning(f'Синхронизация уже выполняется (запущена: {current.triggered_by})')

    run = SyncRun.start(triggered_by='кнопка')
    log_file = _log_path(run.id)
    argv = [
        sys.executable,
        os.path.join(str(settings.BASE_DIR), 'manage.py'),
        'sync_data',
        '--run-id', str(run.id),
    ]
    if start_date and end_date:
        argv += ['--start-date', start_date.date().isoformat(),
                 '--end-date', end_date.date().isoformat()]
    elif months:
        argv += ['--months', str(months)]

    try:
        # Вывод — в файл, а не в никуда: если процесс умрёт, не успев
        # отметиться в базе, это единственное место, где останется след.
        os.makedirs(_logs_dir(), exist_ok=True)
        with open(log_file, 'w', encoding='utf-8') as log_fh:
            subprocess.Popen(
                argv,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        _prune_logs()
    except Exception as e:
        logger.exception('Не удалось запустить синхронизацию')
        run.status = SyncRun.STATUS_ERROR
        run.message = 'Не удалось запустить синхронизацию'
        run.error = str(e)
        run.finished_at = timezone.now()
        run.save(update_fields=['status', 'message', 'error', 'finished_at', 'updated_at'])
        raise

    return run.id


def _logs_dir():
    return getattr(settings, 'SCRIPTS_LOGS_DIR', '/app/scripts_logs')


def _log_path(run_id):
    return os.path.join(_logs_dir(), f'sync_{run_id}.log')


# Сколько логов прогонов оставляем. Ночные пишет монитор проверок, здесь
# копятся только запущенные кнопкой.
KEEP_LOGS = 20


def _prune_logs():
    try:
        files = sorted(glob.glob(os.path.join(_logs_dir(), 'sync_*.log')))
        for old in files[:-KEEP_LOGS]:
            os.unlink(old)
    except Exception:
        logger.exception('Не удалось почистить логи синхронизации')


def execute(triggered_by, start_date=None, end_date=None, months_back=None,
            run_id=None, auto_sync=False, log=None):
    """Проводит синхронизацию и дожидается её. Возвращает код выхода.

    Период задаётся либо парой дат, либо числом месяцев назад — это разные
    обходы: по датам идёт один диапазон, по месяцам задача сама разбивает
    период на месячные куски.
    """
    say = log or (lambda message: None)

    lock_token = SyncLock.acquire_lock('moysklad_sync', locked_by=triggered_by)
    if not lock_token:
        say('Пропуск: синхронизация уже выполняется')
        _close_run(run_id, SyncRun.STATUS_STOPPED, 'Синхронизация уже выполняется')
        return EXIT_BUSY

    # Всё, что после взятия блокировки, — под finally: создание задачи ходит
    # за токеном МойСклада и в кеш, и упавшая на этом синхронизация оставила бы
    # блокировку висеть. Её срок годности — час, и весь этот час пропускались бы
    # и ночные прогоны, и нажатия кнопки.
    heartbeat = None
    run = None
    try:
        run = _attach_run(run_id, triggered_by)
        period = ({'months_back': months_back} if months_back
                  else {'start_date': start_date, 'end_date': end_date})
        task = ParserTask(auto_sync=auto_sync, **period)
        heartbeat = SyncHeartbeat(task, 'moysklad_sync', lock_token, run=run)
        heartbeat.start()

        asyncio.run(task.run())
        if task.progress.status != TaskStatus.COMPLETED:
            say(task.progress.error or task.progress.message or 'Синхронизация не завершена')
            return EXIT_FAILED
        return EXIT_OK
    except Exception as e:
        logger.exception('Ошибка синхронизации')
        say(str(e))
        # Упасть можно и до того, как появилось сердцебиение — тогда закрыть
        # прогон больше некому, и он остался бы «идущим» до срока годности.
        _close_run(run.id if run else run_id, SyncRun.STATUS_ERROR, 'Ошибка синхронизации')
        return EXIT_FAILED
    finally:
        # Останавливаем сердцебиение до снятия блокировки: последний снимок
        # состояния пишет именно оно, и прогон иначе остался бы «идущим».
        if heartbeat:
            heartbeat.stop()
        try:
            SyncLock.release_lock('moysklad_sync', lock_token)
        except Exception:
            logger.exception('Не удалось освободить блокировку синхронизации')


def _attach_run(run_id, triggered_by):
    """Прогон, заведённый кнопкой, или новый — для запуска по расписанию."""
    if run_id:
        run = SyncRun.objects.filter(pk=run_id).first()
        if run:
            return run
        logger.warning('Прогон %s не найден, заводим новый', run_id)
    return SyncRun.start(triggered_by=triggered_by)


def _close_run(run_id, status, message):
    """Закрыть прогон, который так и не начался."""
    if not run_id:
        return
    SyncRun.objects.filter(pk=run_id).update(
        status=status, message=message, finished_at=timezone.now(),
    )
