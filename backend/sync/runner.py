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
# Часть сущностей обновилась, часть нет. Свой код, а не общая единица: иначе
# в журнале cron прогон, где не дались одни отгрузки, выглядит ровно так же,
# как прогон, где не вышло ничего, — а разница между ними и есть весь смысл
# статуса «частично».
EXIT_PARTIAL = 65
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
        # Чистим до запуска: лог только что порождённого процесса удалять
        # нельзя — он продолжит писать в удалённый файл, и следа не останется.
        _prune_logs()
        with open(log_file, 'w', encoding='utf-8') as log_fh:
            subprocess.Popen(
                argv,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
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


def _run_id_in_name(path):
    """Номер прогона из имени лога. Он числовой, и сортировать имена строками
    нельзя: после сотни `sync_100.log` встаёт между `sync_10` и `sync_11`,
    и чистка сносит не старые логи, а первые по алфавиту."""
    name = os.path.basename(path)
    try:
        return int(name[len('sync_'):-len('.log')])
    except ValueError:
        return -1


def _prune_logs():
    try:
        files = sorted(glob.glob(os.path.join(_logs_dir(), 'sync_*.log')),
                       key=_run_id_in_name)
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
    failure = None
    try:
        run = _attach_run(run_id, triggered_by)
        period = ({'months_back': months_back} if months_back
                  else {'start_date': start_date, 'end_date': end_date})
        task = ParserTask(auto_sync=auto_sync, **period)
        heartbeat = SyncHeartbeat(task, 'moysklad_sync', lock_token, run=run)
        heartbeat.start()

        asyncio.run(task.run())
        if task.progress.status == TaskStatus.PARTIAL:
            say(task.progress.message or 'Синхронизация прошла частично')
            return EXIT_PARTIAL
        if task.progress.status != TaskStatus.COMPLETED:
            say(task.progress.error or task.progress.message or 'Синхронизация не завершена')
            return EXIT_FAILED
        return EXIT_OK
    except Exception as e:
        logger.exception('Ошибка синхронизации')
        say(str(e))
        failure = e
        return EXIT_FAILED
    finally:
        # Останавливаем сердцебиение до снятия блокировки: последний снимок
        # состояния пишет именно оно, и прогон иначе остался бы «идущим».
        if heartbeat:
            heartbeat.stop()
        # И только теперь закрываем прогон. Наоборот нельзя: последний снимок
        # сердцебиения пишет объект из памяти, где статус ещё `running`, —
        # отметка об ошибке, поставленная до него, была бы затёрта обратно
        # в «идёт», с пустым finished_at и потерянным текстом ошибки.
        # Упасть можно и до того, как появилось сердцебиение, — тогда закрыть
        # прогон больше некому, и он остался бы «идущим» до срока годности.
        if failure is not None:
            _close_run(run.id if run else run_id, SyncRun.STATUS_ERROR,
                       'Ошибка синхронизации', error=str(failure))
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


def _close_run(run_id, status, message, error=None):
    """Закрыть прогон — по номеру, а не по объекту в памяти: тот к этому
    моменту устарел, его последним трогало сердцебиение."""
    if not run_id:
        return
    fields = {'status': status, 'message': message, 'finished_at': timezone.now()}
    if error is not None:
        fields['error'] = error
    SyncRun.objects.filter(pk=run_id).update(**fields)
