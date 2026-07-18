# api/views/scripts_monitor.py
"""
Мониторинг и запуск автоматизированных скриптов.
"""
import os
import re
import glob
import hashlib
import signal
import threading
import subprocess
import time
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

import logging
logger = logging.getLogger(__name__)

# ─── Конфигурация скриптов ────────────────────────────────────────────────────

SCRIPTS_CONFIG = [
    {
        'id': 'horsebio_health_check',
        'name': 'Health Check',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 09:00',
        'description': 'Проверка себестоимостей, расхождений и аномалий',
        'script': '/app/moysklad/horsebio/02_checks/01_health/scripts/01_health_check.py',
        'args': ['--full'],
        'structured': True,
    },
    {
        'id': 'horsebio_buy_prices',
        'name': 'Закупочные цены',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 ч с 09:00',
        'description': 'Синхронизация buyPrice из FIFO-себестоимости',
        'script': '/app/moysklad/horsebio/01_daemons/02_buy_prices/scripts/01_sync_buy_prices.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_returns',
        'name': 'Возвраты',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 ч с 09:00',
        'description': 'Мониторинг возвратов ВБ и Озон, создание документов',
        'script': '/app/moysklad/horsebio/01_daemons/03_returns/scripts/01_monitor_returns.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'starpony_cost_prices',
        'name': 'Себестоимость',
        'account': 'StarPony',
        'schedule': 'Каждые 5 ч с 09:00',
        'description': 'FIFO → тип цены "Себестоимость"',
        'script': '/app/moysklad/starpony/01_daemons/01_cost_prices/scripts/01_sync_cost_prices.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_deadlines',
        'name': 'Сроки оплаты',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 09:00',
        'description': 'Мониторинг просроченных и скоро истекающих оплат',
        'script': '/app/moysklad/horsebio/01_daemons/05_payment_deadline/scripts/01_check_deadlines.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'starpony_deadlines',
        'name': 'Сроки оплаты',
        'account': 'StarPony',
        'schedule': 'Ежедн. в 09:00',
        'description': 'Мониторинг просроченных и скоро истекающих оплат',
        'script': '/app/moysklad/starpony/01_daemons/02_payment_deadline/scripts/01_check_deadlines.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'starpony_production',
        'name': 'Производственные задания',
        'account': 'StarPony',
        'schedule': 'Вручную',
        'description': 'Создание ПЗ из открытых заказов без задания',
        'script': '/app/moysklad/starpony/03_updates/02_production_tasks/scripts/create_production_task.py',
        'args': ['--all'],
    },
]

SCRIPTS_BY_ID = {s['id']: s for s in SCRIPTS_CONFIG}

# ─── Авторизация ──────────────────────────────────────────────────────────────

def scripts_auth(view_func):
    """Декоратор: только суперпользователь или X-Cron-Secret заголовок."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        cron_secret = getattr(settings, 'CRON_SECRET', '')
        if cron_secret and request.headers.get('X-Cron-Secret') == cron_secret:
            return view_func(request, *args, **kwargs)
        return JsonResponse({'status': 'error', 'message': 'Требуется авторизация'}, status=401)
    return wrapper


def scripts_auth_basic(view_func):
    """Декоратор: любой авторизованный пользователь или X-Cron-Secret заголовок."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        cron_secret = getattr(settings, 'CRON_SECRET', '')
        if cron_secret and request.headers.get('X-Cron-Secret') == cron_secret:
            return view_func(request, *args, **kwargs)
        return JsonResponse({'status': 'error', 'message': 'Требуется авторизация'}, status=401)
    return wrapper


def _starpony_access_denied(request, script_id):
    """Возвращает 403 если скрипт StarPony и пользователь не суперпользователь."""
    script = SCRIPTS_BY_ID.get(script_id)
    if script and script.get('account') == 'StarPony':
        is_superuser = request.user.is_authenticated and request.user.is_superuser
        cron_secret = getattr(settings, 'CRON_SECRET', '')
        if not is_superuser and not (cron_secret and request.headers.get('X-Cron-Secret') == cron_secret):
            return JsonResponse({'status': 'error', 'message': 'Нет доступа'}, status=403)
    return None

# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _logs_dir():
    return getattr(settings, 'SCRIPTS_LOGS_DIR', '/app/scripts_logs')


def _pid_file(script_id):
    return os.path.join(_logs_dir(), f'{script_id}.pid')


def _exit_file(log_file):
    return log_file + '.exit'


def _log_filename(script_id, timestamp):
    return os.path.join(_logs_dir(), f'{script_id}_{timestamp}.log')


# Скрипт проверки здоровья — единственный со структурированными результатами и исключениями
HEALTH_CHECK_SCRIPT_ID = 'horsebio_health_check'


def _results_file(script_id, timestamp):
    return os.path.join(_logs_dir(), f'{script_id}_{timestamp}.results.json')


_NORMALIZE_RE = re.compile(
    r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?'  # ISO datetime
    r'|\d{2}\.\d{2}\.\d{4}'                           # DD.MM.YYYY
    r'|\d+[.,]\d+р'                                   # FIFO-цены: 30.38р
    r'|[-−]?\d+[.,]\d+\s*%'                           # отклонения: -6.5%
    r'|\b\d+\s*ед\b'                                  # запасы: 397 ед
    r'|\d+[.,]\d+\s*сек\b'                            # тайминг: 42.3 сек
)

# Версия нормализации — при изменении инвалидирует кэш .hash файлов
_HASH_VERSION = 'v2:'


def _content_hash(log_file):
    """MD5 нормализованного содержимого лога.
    Кэшируется в .log.hash; префикс версии инвалидирует устаревший кэш.
    """
    hash_file = log_file + '.hash'
    if os.path.exists(hash_file):
        try:
            with open(hash_file) as f:
                cached = f.read().strip()
            if cached.startswith(_HASH_VERSION):
                return cached[len(_HASH_VERSION):]
        except Exception:
            pass
    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        normalized = _NORMALIZE_RE.sub('', content)
        h = hashlib.md5(normalized.encode()).hexdigest()
        try:
            with open(hash_file, 'w') as f:
                f.write(_HASH_VERSION + h)
        except Exception:
            pass
        return h
    except Exception:
        return None


def _get_runs(script_id):
    """Возвращает список запусков (сортировка: новые первыми).
    Каждый запуск содержит флаг has_changes — отличается ли содержимое от предыдущего.
    """
    pattern = os.path.join(_logs_dir(), f'{script_id}_*.log')
    files = sorted(glob.glob(pattern), reverse=True)[:20]
    running_now = _is_running(script_id)
    runs = []
    hashes = []
    for i, f in enumerate(files):
        basename = os.path.basename(f)
        run_id = basename[len(script_id) + 1:-4]
        exit_code = _get_exit_code(f)
        # Если это не текущий запуск и exit-кода нет — считаем успехом если лог не пустой.
        if exit_code is None and not (i == 0 and running_now):
            exit_code = 0 if os.path.getsize(f) > 0 else None
        size = os.path.getsize(f)
        mtime = os.path.getmtime(f)
        h = _content_hash(f) if exit_code is not None else None
        hashes.append(h)
        runs.append({
            'run_id': run_id,
            'timestamp': run_id.replace('_', ' ').replace('-', ':', 2),
            'exit_code': exit_code,
            'size': size,
            'finished_at': datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'has_changes': True,  # будет пересчитан ниже
        })
    # Проставляем has_changes: сравниваем хэш текущего с предыдущим (более старым)
    for i, run in enumerate(runs):
        cur = hashes[i]
        prev = hashes[i + 1] if i + 1 < len(hashes) else None
        run['has_changes'] = (cur is None) or (prev is None) or (cur != prev)
    return runs


def _get_exit_code(log_file):
    exit_file = _exit_file(log_file)
    if not os.path.exists(exit_file):
        return None
    try:
        with open(exit_file) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _is_running(script_id):
    pid_file = _pid_file(script_id)
    if not os.path.exists(pid_file):
        return False
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # Сигнал 0 — просто проверка существования процесса
        return True
    except (ProcessLookupError, PermissionError):
        # Процесс уже завершился, удаляем устаревший файл
        try:
            os.unlink(pid_file)
        except Exception:
            pass
        return False
    except Exception:
        return False


def _pid_is_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _get_latest_run(script_id):
    runs = _get_runs(script_id)
    return runs[0] if runs else None


def _run_script_async(script_id, script_path, args):
    """Запускает скрипт в фоне, пишет лог и exit-код."""
    os.makedirs(_logs_dir(), exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file = _log_filename(script_id, timestamp)
    pid_file = _pid_file(script_id)

    # Структурированные скрипты пишут находки в .results.json (для страницы /checks).
    # health_check дополнительно: исключения хранятся в БД — регенерируем data/*.json перед запуском.
    run_args = list(args)
    results_file = None
    is_structured = SCRIPTS_BY_ID.get(script_id, {}).get('structured')
    if script_id == HEALTH_CHECK_SCRIPT_ID:
        try:
            from api.services.health_checks import cleanup_expired_exceptions, export_exceptions_to_json
            cleanup_expired_exceptions()
            export_exceptions_to_json()
        except Exception as e:
            logger.error('Не удалось экспортировать исключения health_check: %s', e)
    if is_structured:
        results_file = _results_file(script_id, timestamp)
        run_args = run_args + ['--results-out', results_file]

    started_at = time.time()
    try:
        log_fh = open(log_file, 'w', encoding='utf-8')
        proc = subprocess.Popen(
            ['python3', script_path] + run_args,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as e:
        logger.error(f'Ошибка запуска скрипта {script_id}: {e}')
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f'\n[ОШИБКА ЗАПУСКА] {e}\n')
            with open(_exit_file(log_file), 'w') as f:
                f.write('-1')
        except Exception:
            pass
        return timestamp

    # Сохраняем PID
    with open(pid_file, 'w') as f:
        f.write(str(proc.pid))

    # Поток-наблюдатель: ждёт завершения и записывает exit-код
    def _wait(proc, log_fh, log_file, pid_file):
        proc.wait()
        log_fh.close()
        try:
            with open(_exit_file(log_file), 'w') as f:
                f.write(str(proc.returncode))
        except Exception:
            pass
        try:
            os.unlink(pid_file)
        except Exception:
            pass
        # Структурированные скрипты: разбираем .results.json в БД
        if results_file:
            try:
                from api.services.health_checks import ingest_results_file
                ingest_results_file(
                    script_id, timestamp, results_file,
                    exit_code=proc.returncode,
                    duration_sec=round(time.time() - started_at, 1),
                )
            except Exception as e:
                logger.error('Не удалось разобрать результаты %s: %s', script_id, e)
        # Удаляем старые логи (оставляем последние 20)
        _cleanup_old_logs(script_id)

    t = threading.Thread(target=_wait, args=(proc, log_fh, log_file, pid_file), daemon=True)
    t.start()

    return timestamp


# Таймер пишет "\r  ⏱  Xс   " (без \n), продукт пишет сразу за ним.
# В файле это выглядит как один \r-сегмент: "  ⏱  1с     [  2/50] Product..."
# Паттерн: ⏱ + пробелы + время (N с или N м N с) + пробелы
# Таймер пишет "\r  ⏱  {t}   " — ровно 3 пробела в конце.
# Продукт пишет сразу за ним со своим отступом (2 или 4 пробела).
# \s{3} срезает ровно 3 пробела таймера, оставляя отступ продукта нетронутым.
_TIMER_PREFIX_RE = re.compile(r'^\s*⏱\s+(?:\d+м\s+)?\d+с\s{3}')


def _strip_timer_prefix(seg):
    """Убирает таймер-префикс '  ⏱  1с   ' из сегмента.
    Возвращает остаток с оригинальным отступом продукта.
    """
    m = _TIMER_PREFIX_RE.match(seg)
    if not m:
        return seg.rstrip()
    return seg[m.end():].rstrip()  # отступ продукта сохранён, ничего не добавляем


def _process_terminal_output(text):
    """Очищает вывод скриптов от таймер-строк и \r-мусора.

    Скрипт пишет прогресс через end='\\r', а фоновый поток таймера пишет
    "\\r  ⏱  Nс   " конкурентно. В файле всё это склеивается в один \r-сегмент:
    "  ⏱  1с     [  2/50] L-метионин...". Функция убирает таймер-префикс,
    оставляя только строки с реальным прогрессом (каждый товар — отдельная строка).
    """
    text = text.replace('\r\n', '\n')  # нормализуем Windows CRLF
    result = []
    prev_was_blank = False

    for nl_segment in text.split('\n'):
        if '\r' not in nl_segment:
            line = nl_segment.rstrip()
            if not line:
                if not prev_was_blank:
                    result.append('')
                prev_was_blank = True
            else:
                result.append(line)
                prev_was_blank = False
            continue

        # Строка с \r: каждый сегмент — один шаг прогресса
        for seg in nl_segment.split('\r'):
            clean = _strip_timer_prefix(seg)
            if not clean:
                continue  # пустой сегмент или чистый таймер без контента
            result.append(clean)
            prev_was_blank = False

    while result and not result[-1]:
        result.pop()

    return '\n'.join(result)


def _cleanup_old_logs(script_id):
    pattern = os.path.join(_logs_dir(), f'{script_id}_*.log')
    files = sorted(glob.glob(pattern))
    for old in files[:-20]:
        try:
            os.unlink(old)
            for ext in (_exit_file(old), old + '.hash', old[:-4] + '.results.json'):
                if os.path.exists(ext):
                    os.unlink(ext)
        except Exception:
            pass

# ─── Views ────────────────────────────────────────────────────────────────────

@scripts_auth_basic
def scripts_list(request):
    """GET /api/scripts/ — список скриптов со статусом последнего запуска.

    Суперпользователь видит все скрипты; остальные — только HorseBio.
    """
    is_superuser = request.user.is_authenticated and request.user.is_superuser
    result = []
    for script in SCRIPTS_CONFIG:
        if script.get('account') == 'StarPony' and not is_superuser:
            continue
        sid = script['id']
        latest = _get_latest_run(sid)
        running = _is_running(sid)
        result.append({
            **{k: script[k] for k in ('id', 'name', 'account', 'schedule', 'description')},
            'is_running': running,
            'last_run': latest,
            'script_exists': os.path.exists(script['script']),
        })
    return JsonResponse({'scripts': result})


@scripts_auth_basic
def script_runs(request, script_id):
    """GET /api/scripts/{id}/runs/ — последние 20 запусков."""
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied
    runs = _get_runs(script_id)
    return JsonResponse({'runs': runs, 'is_running': _is_running(script_id)})


@scripts_auth_basic
def script_log(request, script_id, run_id):
    """GET /api/scripts/{id}/runs/{run_id}/log/ — содержимое лога.

    Поддерживает ?offset=N для инкрементального polling во время выполнения.
    """
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied

    log_file = _log_filename(script_id, run_id)
    if not os.path.exists(log_file):
        return JsonResponse({'content': '', 'offset': 0, 'is_running': False, 'exit_code': None})

    offset = int(request.GET.get('offset', 0))

    try:
        # newline='' — отключаем universal newlines, чтобы \r не превращался в \n
        with open(log_file, 'r', encoding='utf-8', errors='replace', newline='') as f:
            raw = f.read()
        content = _process_terminal_output(raw)
        new_offset = len(content)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    # Считаем этот запуск "текущим" только если он последний
    latest = _get_latest_run(script_id)
    is_current_run = latest and latest['run_id'] == run_id
    running = is_current_run and _is_running(script_id)

    return JsonResponse({
        'content': content,
        'offset': new_offset,
        'is_running': running,
        'exit_code': _get_exit_code(log_file),
    })


@csrf_exempt
@scripts_auth_basic
@require_http_methods(['POST'])
def script_stop(request, script_id):
    """POST /api/scripts/{id}/stop/ — остановить запущенный скрипт."""
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied

    pid_file = _pid_file(script_id)
    if not os.path.exists(pid_file):
        return JsonResponse({'status': 'ok', 'message': 'Скрипт уже завершён'})

    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())

        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            raise
        except Exception:
            pgid = None
            os.kill(pid, signal.SIGTERM)

        for _ in range(15):
            if not _pid_is_alive(pid):
                return JsonResponse({'status': 'ok', 'message': 'Скрипт остановлен'})
            time.sleep(0.1)

        try:
            if pgid is not None:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return JsonResponse({'status': 'ok', 'message': 'Скрипт остановлен'})

        return JsonResponse({'status': 'ok', 'message': 'Скрипт принудительно остановлен'})
    except ProcessLookupError:
        try:
            os.unlink(pid_file)
        except Exception:
            pass
        return JsonResponse({'status': 'ok', 'message': 'Процесс уже завершён'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@scripts_auth_basic
@require_http_methods(['POST'])
def script_run_delete(request, script_id, run_id):
    """POST /api/scripts/{id}/runs/{run_id}/delete/ — удалить лог запуска."""
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied

    # Нельзя удалять лог текущего запуска
    if _is_running(script_id):
        latest = _get_latest_run(script_id)
        if latest and latest['run_id'] == run_id:
            return JsonResponse({'status': 'error', 'message': 'Нельзя удалить лог запущенного скрипта'}, status=409)

    log_file = _log_filename(script_id, run_id)
    if not os.path.exists(log_file):
        return JsonResponse({'status': 'error', 'message': 'Лог не найден'}, status=404)

    try:
        os.unlink(log_file)
        for ext in (_exit_file(log_file), log_file + '.hash'):
            if os.path.exists(ext):
                os.unlink(ext)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'ok'})


@csrf_exempt
@scripts_auth_basic
@require_http_methods(['POST'])
def script_run_now(request, script_id):
    """POST /api/scripts/{id}/run/ — запустить скрипт немедленно."""
    script = SCRIPTS_BY_ID.get(script_id)
    if not script:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied

    if _is_running(script_id):
        return JsonResponse({'status': 'error', 'message': 'Скрипт уже запущен'}, status=409)

    if not os.path.exists(script['script']):
        return JsonResponse({
            'status': 'error',
            'message': f'Файл скрипта не найден: {script["script"]}'
        }, status=400)

    run_id = _run_script_async(script_id, script['script'], script['args'])

    return JsonResponse({
        'status': 'ok',
        'run_id': run_id,
        'message': f'Скрипт {script["name"]} запущен',
    })
