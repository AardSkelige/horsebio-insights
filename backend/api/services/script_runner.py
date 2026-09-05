# api/services/script_runner.py
"""
Запуск скриптов проверок — единственное место, где они порождаются.

Cron зовёт `manage.py run_check <id>` внутри контейнера, кнопка в интерфейсе
порождает ту же команду отдельным процессом. Веб-процесс за прогоном больше
не следит, и это главное: раньше завершения ждал поток внутри Django. Он жил,
пока жив `runserver` — один процесс на сутки. Под gunicorn воркер
перезапускается по счётчику запросов, поток-наблюдатель умирает вместе с ним,
и скрипт доработал бы, а отметку о завершении записать стало бы некому:
в интерфейсе он остался бы «выполняется» навсегда, без единой ошибки в логах.

Три файла на прогон в SCRIPTS_LOGS_DIR:

    <id>_<run_id>.log        вывод скрипта
    <id>_<run_id>.log.exit   код выхода — появляется последним, признак конца
    <id>.pid                 pid идущего run_check, он же замок от наложения

Замок именно pid-файл, а не флаг в базе: у него есть проверка живости
(`kill -0`), поэтому убитый прогон не оставляет вечной блокировки.
"""
import os
import sys
import glob
import time
import signal
import logging
import threading
import subprocess
from datetime import datetime

from django.conf import settings

from api.services.scripts_registry import (
    SCRIPTS_BY_ID, HEALTH_CHECK_SCRIPT_ID, script_timeout,
)

logger = logging.getLogger(__name__)

# Сколько логов на скрипт оставляем.
MAX_RUNS_KEPT = 20

# Коды выхода run_check. Пропуск отделён от ошибки своим кодом: иначе
# «предыдущий прогон ещё идёт» неотличимо от «скрипт упал», и каждый тик
# пятиминутной задачи поднимал бы ложную тревогу, пока идёт долгий прогон.
EXIT_BUSY = 75
EXIT_UNKNOWN = 2
EXIT_TIMEOUT = 124  # как у timeout(1)
EXIT_LAUNCH_FAILED = 3

# Чем кончилась остановка. Тексты здесь же: обе страницы («Проверки»
# и монитор скриптов) показывают одно и то же, и разъезжаться им незачем.
STOP_IDLE = 'idle'
STOP_GONE = 'gone'
STOP_STOPPED = 'stopped'
STOP_KILLED = 'killed'

STOP_MESSAGES = {
    STOP_IDLE: 'Скрипт уже завершён',
    STOP_GONE: 'Процесс уже завершён',
    STOP_STOPPED: 'Скрипт остановлен',
    STOP_KILLED: 'Скрипт принудительно остановлен',
}

# Маска даты в имени лога: {script_id}_2026-08-19_14-20-46.log. Нужна именно
# маска, а не '*': id одного скрипта бывает префиксом другого (horsebio_returns
# и horsebio_returns_ozon_enrich), и по '*' они разбирают логи друг друга.
RUN_ID_GLOB = '????-??-??_??-??-??'


# ─── Пути ─────────────────────────────────────────────────────────────────────

def logs_dir():
    return getattr(settings, 'SCRIPTS_LOGS_DIR', '/app/scripts_logs')


def log_filename(script_id, run_id):
    return os.path.join(logs_dir(), f'{script_id}_{run_id}.log')


def exit_file(log_file):
    return log_file + '.exit'


def results_filename(script_id, run_id):
    return os.path.join(logs_dir(), f'{script_id}_{run_id}.results.json')


def pid_file(script_id):
    return os.path.join(logs_dir(), f'{script_id}.pid')


def new_run_id():
    return datetime.now().strftime('%Y-%m-%d_%H-%M-%S')


# ─── Замок ────────────────────────────────────────────────────────────────────

# Процессы, порождённые кнопкой. Их надо прибирать: завершившийся, но не
# дождавшийся родителя процесс остаётся зомби, а зомби для `kill -0` живой —
# и карточка навсегда осталась бы «выполняется», а новый прогон упирался бы
# в занятый замок. Родитель здесь — веб-процесс, поэтому и прибираем в нём,
# на каждом обращении к замку.
_launched = []
_launched_lock = threading.Lock()


def _reap_finished():
    with _launched_lock:
        for proc in list(_launched):
            if proc.poll() is not None:
                _launched.remove(proc)


def pid_is_alive(pid):
    try:
        os.kill(pid, 0)  # Сигнал 0 — просто проверка существования процесса
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _proc_start_time(pid):
    """Момент запуска процесса (поле 22 в /proc/<pid>/stat) или None.

    Нужен, чтобы отличить наш процесс от чужого с тем же номером. Замок лежит
    в томе `scripts_logs` и переживает пересоздание контейнера, а номера
    процессов в новом контейнере начинаются заново: без этой проверки замок
    от оборванного прогона указывал бы на живой gunicorn — и проверка молча
    перестала бы запускаться, отмечаясь в журнале безобидным «пропуском».
    Вне Linux (машина разработчика) /proc нет, и тогда проверка пропускается.
    """
    try:
        with open(f'/proc/{pid}/stat', 'rb') as f:
            fields = f.read().rsplit(b')', 1)[1].split()
        return int(fields[19])
    except Exception:
        return None


def _lock_payload(pid):
    start = _proc_start_time(pid)
    return f'{pid} {start}' if start is not None else str(pid)


def read_lock(script_id):
    """(pid, момент запуска) из замка. Момент — None, если он не записан."""
    try:
        with open(pid_file(script_id)) as f:
            parts = f.read().split()
        pid = int(parts[0])
        start = int(parts[1]) if len(parts) > 1 else None
        return pid, start
    except Exception:
        return None, None


def read_pid(script_id):
    return read_lock(script_id)[0]


def holder_is_alive(pid, start=None):
    """Жив ли владелец замка. Совпадение номера без совпадения момента
    запуска — это чужой процесс, занявший освободившийся номер."""
    if pid is None or pid <= 0 or not pid_is_alive(pid):
        return False
    if start is not None:
        current = _proc_start_time(pid)
        if current is not None and current != start:
            return False
    return True


def _write_pid(script_id, pid):
    with open(pid_file(script_id), 'w') as f:
        f.write(_lock_payload(pid))


def _clear_pid(script_id):
    try:
        os.unlink(pid_file(script_id))
    except Exception:
        pass


def _claim_lock(script_id, pid):
    """Занять замок. False — занят живым прогоном.

    Создание с O_EXCL, а не «прочитать и записать»: между чтением и записью
    успевает вклиниться второй запуск, и тогда оба считают себя единственными.
    """
    path = pid_file(script_id)
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            holder, start = read_lock(script_id)
            if holder == pid:
                # Замок поставила кнопка, и поставила его на нас же.
                _write_pid(script_id, pid)
                return True
            if holder_is_alive(holder, start):
                return False
            _clear_pid(script_id)  # мёртвый владелец — вытесняем и пробуем снова
            continue
        with os.fdopen(fd, 'w') as f:
            f.write(_lock_payload(pid))
        return True
    return False


def is_running(script_id):
    _reap_finished()
    pid, start = read_lock(script_id)
    if pid is None:
        return False
    if holder_is_alive(pid, start):
        return True
    _clear_pid(script_id)  # владельца больше нет, замок устарел
    return False


def child_pid_file(script_id):
    """Замок самого скрипта. Он живёт в своей группе процессов, и чтобы его
    было кем остановить, когда run_check уже убит, номер нужен отдельно."""
    return os.path.join(logs_dir(), f'{script_id}.script.pid')


# ─── Чистка ───────────────────────────────────────────────────────────────────

def cleanup_old_logs(script_id):
    pattern = os.path.join(logs_dir(), f'{script_id}_{RUN_ID_GLOB}.log')
    files = sorted(glob.glob(pattern))
    for old in files[:-MAX_RUNS_KEPT]:
        try:
            os.unlink(old)
            for extra in (exit_file(old), old + '.hash', old[:-4] + '.results.json'):
                if os.path.exists(extra):
                    os.unlink(extra)
        except Exception:
            pass


# ─── Остановка ────────────────────────────────────────────────────────────────

def stop(script_id, grace_sec=3.0):
    """Останавливает идущий прогон. Возвращает одно из STOP_*.

    Сигнал идёт и скрипту, и run_check: скрипт живёт в своей группе процессов,
    а отметку о завершении пишет run_check. Добить одного без другого значит
    либо оставить прогон без кода выхода, либо оставить работать осиротевший
    скрипт — а он через пять минут встретится со своим же новым запуском.
    Пауза перед SIGKILL нужна run_check, чтобы успеть записать итог.
    """
    pid, start = read_lock(script_id)
    if pid is None:
        return STOP_IDLE
    if not holder_is_alive(pid, start):
        _clear_pid(script_id)
        _clear_child_pid(script_id)
        _mark_killed(script_id, 'прогон оборвался, не записав итог')
        return STOP_GONE

    _signal_run(script_id, pid, signal.SIGTERM)
    deadline = time.time() + grace_sec
    while time.time() < deadline:
        _reap_finished()
        # Конец прогона — это снятый замок: run_check убирает его последним,
        # уже записав код выхода. Ждём именно этого, а не смерти процесса:
        # процесс успевает побыть зомби, и по `kill -0` он ещё «живой».
        if read_pid(script_id) != pid:
            return STOP_STOPPED
        if not holder_is_alive(pid, start):
            # Умер, не прибрав за собой: записать код выхода было некому.
            _clear_pid(script_id)
            _clear_child_pid(script_id)
            _mark_killed(script_id, 'прогон снят вручную')
            return STOP_STOPPED
        time.sleep(0.1)

    _signal_run(script_id, pid, signal.SIGKILL)
    _clear_pid(script_id)
    _clear_child_pid(script_id)
    _mark_killed(script_id, 'прогон снят вручную')
    return STOP_KILLED


def _signal_run(script_id, owner_pid, sig):
    """Сигнал обоим: сперва скрипту, потом run_check.

    Порядок важен для мягкой остановки — скрипт умирает, run_check это видит
    и записывает код выхода штатно.
    """
    child, child_start = read_child_lock(script_id)
    if holder_is_alive(child, child_start):
        _signal_pid(child, sig)
    _signal_pid(owner_pid, sig)


def read_child_lock(script_id):
    try:
        with open(child_pid_file(script_id)) as f:
            parts = f.read().split()
        return int(parts[0]), (int(parts[1]) if len(parts) > 1 else None)
    except Exception:
        return None, None


def _write_child_pid(script_id, pid):
    try:
        with open(child_pid_file(script_id), 'w') as f:
            f.write(_lock_payload(pid))
    except Exception:
        logger.exception('Не удалось записать номер процесса скрипта %s', script_id)


def _clear_child_pid(script_id):
    try:
        os.unlink(child_pid_file(script_id))
    except Exception:
        pass


def _signal_pid(pid, sig):
    """Сигнал группе процесса: скрипт может успеть породить своих детей,
    и они должны уйти вместе с ним."""
    if pid is None or pid <= 0:
        return
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    except Exception:
        pgid = 0
    # killpg(0) бьёт по собственной группе — то есть по веб-процессу целиком.
    # Ноль возвращается, когда лидер группы не виден в нашем пространстве
    # имён; тогда шлём сигнал одному процессу, а не группе.
    if pgid > 0 and pgid != os.getpgid(0):
        try:
            os.killpg(pgid, sig)
            return
        except ProcessLookupError:
            return
        except Exception:
            pass
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass
    except Exception:
        logger.exception('Не удалось послать сигнал процессу %s', pid)


def _mark_killed(script_id, reason):
    """Проставить код выхода последнему прогону, если его некому записать.

    Прогон без кода выхода страница считает удачным — лог не пуст, значит
    отработал. Поэтому оборванный прогон обязан оставить след.
    """
    pattern = os.path.join(logs_dir(), f'{script_id}_{RUN_ID_GLOB}.log')
    logs = sorted(glob.glob(pattern), reverse=True)
    if not logs:
        return
    latest = logs[0]
    if os.path.exists(exit_file(latest)):
        return
    try:
        _append(latest, f'\n[ОСТАНОВЛЕН] {reason}\n')
        with open(exit_file(latest), 'w') as f:
            f.write(str(-signal.SIGKILL))
    except Exception:
        logger.exception('Не удалось отметить остановку %s', script_id)


# ─── Запуск из интерфейса ─────────────────────────────────────────────────────

def launch(script_id):
    """Порождает `manage.py run_check` и сразу возвращает run_id.

    Кнопка «Запустить» ведёт себя как ночной прогон: место запуска одно,
    и разница между ними — только в том, кто нажал.
    """
    os.makedirs(logs_dir(), exist_ok=True)
    run_id = new_run_id()
    log_file = log_filename(script_id, run_id)
    manage_py = os.path.join(str(settings.BASE_DIR), 'manage.py')

    # Лог заводим здесь и отдаём команде тот же файл: между ответом страницы
    # и первой строкой скрипта проходит секунда-другая — Django в новом
    # процессе поднимается не мгновенно. Пустой файл лучше отсутствующего:
    # страница показывает «выполняется», а не «лог не найден». Сюда же
    # попадёт трассировка, если сама команда не поднимется.
    try:
        with open(log_file, 'a', encoding='utf-8') as log_fh:
            proc = subprocess.Popen(
                [sys.executable, manage_py, 'run_check', script_id, '--run-id', run_id],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except Exception as e:
        # Прогон, который не начался, обязан быть виден как неудачный: без
        # кода выхода страница показала бы пустой, но успешный запуск.
        logger.error('Не удалось запустить run_check %s: %s', script_id, e)
        _append(log_file, f'\n[ОШИБКА ЗАПУСКА] {e}\n')
        with open(exit_file(log_file), 'w') as f:
            f.write(str(EXIT_LAUNCH_FAILED))
        return run_id

    with _launched_lock:
        _launched.append(proc)

    # Замок ставим сразу, до того как команда успела подняться: до этого
    # момента прогон обязан выглядеть идущим, иначе страница решит, что он
    # уже кончился. Команда узнаёт в замке свой собственный номер и не
    # считает его чужим. Если замок успел занять прогон по расписанию —
    # не отбираем: команда увидит это сама и отметит пропуск.
    _claim_lock(script_id, proc.pid)
    return run_id


# ─── Запуск и ожидание (то, что делает сама команда) ──────────────────────────

def execute(script_id, run_id=None, timeout=None, log=None):
    """Запускает скрипт, ждёт его и записывает итог. Возвращает код выхода."""
    say = log or (lambda message: None)
    script = SCRIPTS_BY_ID.get(script_id)
    if not script:
        say(f'Неизвестный скрипт: {script_id}')
        return EXIT_UNKNOWN
    if not os.path.exists(script['script']):
        say(f'Файл скрипта не найден: {script["script"]}')
        return EXIT_UNKNOWN

    os.makedirs(logs_dir(), exist_ok=True)

    # Свой же номер в замке — это запуск из интерфейса: кнопка поставила
    # замок на нас до того, как Django здесь успел подняться.
    if not _claim_lock(script_id, os.getpid()):
        owner = read_pid(script_id)
        say(f'Пропуск: предыдущий прогон {script_id} ещё идёт (pid {owner})')
        # Если лог этому прогону уже завела кнопка — отмечаем пропуск: без
        # кода выхода он выглядел бы на странице удачным.
        if run_id and os.path.exists(log_filename(script_id, run_id)):
            with open(exit_file(log_filename(script_id, run_id)), 'w') as f:
                f.write(str(EXIT_BUSY))
        return EXIT_BUSY

    run_id = run_id or new_run_id()
    log_file = log_filename(script_id, run_id)
    argv = [sys.executable, '-u', script['script']] + list(script['args'])

    # Структурированные скрипты пишут находки в .results.json — из него
    # страница /checks и берёт карточки.
    results_file = None
    if script.get('structured'):
        results_file = results_filename(script_id, run_id)
        argv += ['--results-out', results_file]

    # Исключения health_check хранятся в БД, а скрипт читает их из файлов —
    # выгружаем перед запуском.
    if script_id == HEALTH_CHECK_SCRIPT_ID:
        _export_health_exceptions()

    started_at = time.time()
    code = EXIT_LAUNCH_FAILED
    try:
        # -u: без буферизации. Иначе вывод копится блоками по 4 КБ и лог
        # на странице выглядит замершим, пока скрипт на самом деле работает.
        with open(log_file, 'a', encoding='utf-8') as log_fh:
            proc = subprocess.Popen(
                argv,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            _write_child_pid(script_id, proc.pid)
            code = _wait(proc, timeout or script_timeout(script_id), log_file)
    except Exception as e:
        logger.error('Ошибка запуска скрипта %s: %s', script_id, e)
        _append(log_file, f'\n[ОШИБКА ЗАПУСКА] {e}\n')
        say(f'Ошибка запуска: {e}')
    finally:
        _finalize(script_id, run_id, code, started_at, results_file)
    return code


def _wait(proc, timeout, log_file):
    """Ждёт скрипт, пробрасывая ему сигналы остановки.

    Сигнал приходит сюда, а не скрипту: кнопка «Стоп» бьёт по группе процессов
    из pid-файла, а при остановке контейнера сигнал шлёт docker. Скрипт живёт
    в своей группе, и только здесь известно, кому этот сигнал переадресовать —
    и кто потом запишет код выхода.
    """
    def forward(signum, frame):
        _signal_pid(proc.pid, signal.SIGTERM)

    # signal.signal доступен только главному потоку. Обычно execute и зовут
    # оттуда — из команды, но сервис не должен падать, если его позовут иначе.
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            previous[sig] = signal.signal(sig, forward)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _signal_pid(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            _signal_pid(proc.pid, signal.SIGKILL)
            proc.wait()
        _append(log_file, f'\n[СНЯТ ПО СРОКУ] прогон шёл дольше {timeout} с\n')
        return EXIT_TIMEOUT
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _finalize(script_id, run_id, code, started_at, results_file):
    """Отметка о завершении. Порядок важен: код выхода — признак конца прогона
    для страницы, и он должен появиться раньше, чем исчезнет замок."""
    log_file = log_filename(script_id, run_id)
    try:
        with open(exit_file(log_file), 'w') as f:
            f.write(str(code))
    except Exception:
        logger.exception('Не удалось записать код выхода %s', script_id)
    _clear_child_pid(script_id)
    _clear_pid(script_id)

    if results_file:
        try:
            from api.services.health_checks import ingest_results_file
            ingest_results_file(
                script_id, run_id, results_file,
                exit_code=code,
                duration_sec=round(time.time() - started_at, 1),
            )
        except Exception as e:
            logger.error('Не удалось разобрать результаты %s: %s', script_id, e)

    cleanup_old_logs(script_id)


def _export_health_exceptions():
    try:
        from api.services.health_checks import (
            cleanup_expired_exceptions, export_exceptions_to_json,
        )
        cleanup_expired_exceptions()
        export_exceptions_to_json()
    except Exception as e:
        logger.error('Не удалось экспортировать исключения health_check: %s', e)


def _append(log_file, text):
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(text)
    except Exception:
        pass
