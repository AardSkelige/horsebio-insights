# api/views/scripts_monitor.py
"""
Мониторинг автоматизированных скриптов: список, история, логи, остановка.

Сам запуск живёт в api/services/script_runner.py и идёт отдельным процессом
(`manage.py run_check`) — веб только порождает его и читает то, что он оставил
в файлах. Реестр задач — в api/services/scripts_registry.py.
"""
import os
import re
import glob
import hashlib
import secrets
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods

from api.services import script_runner
from api.services.scripts_registry import (
    SCRIPTS_CONFIG, SCRIPTS_BY_ID, HEALTH_CHECK_SCRIPT_ID,
)

import logging
logger = logging.getLogger(__name__)


# ─── Авторизация ──────────────────────────────────────────────────────────────

def _has_valid_cron_secret(request):
    """Проверить machine-to-machine секрет без утечки по времени сравнения."""
    configured_secret = getattr(settings, 'CRON_SECRET', '')
    supplied_secret = request.headers.get('X-Cron-Secret', '')
    return bool(
        configured_secret
        and supplied_secret
        and secrets.compare_digest(supplied_secret, configured_secret)
    )


def scripts_auth(view_func):
    """Только суперпользователь или запрос с X-Cron-Secret."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        if _has_valid_cron_secret(request):
            return view_func(request, *args, **kwargs)
        status = 403 if request.user.is_authenticated else 401
        return JsonResponse({'status': 'error', 'message': 'Нет доступа'}, status=status)
    return wrapper


def scripts_mutation_auth(view_func):
    """Авторизация изменений: cron по секрету, администратор — с CSRF.

    Внешний cron не использует cookie-сессию, поэтому CSRF ему не нужен. Для
    браузерной сессии суперпользователя CSRF остаётся обязательным.
    """
    csrf_protected_view = csrf_protect(view_func)

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if _has_valid_cron_secret(request):
            return view_func(request, *args, **kwargs)
        if request.user.is_authenticated and request.user.is_superuser:
            return csrf_protected_view(request, *args, **kwargs)
        status = 403 if request.user.is_authenticated else 401
        return JsonResponse({'status': 'error', 'message': 'Нет доступа'}, status=status)

    # Глобальный middleware пропускает wrapper; ветка session auth выше явно
    # прогоняется через csrf_protect, а machine-to-machine запрос — нет.
    return csrf_exempt(wrapper)


def scripts_auth_basic(view_func):
    """Декоратор: любой авторизованный пользователь или X-Cron-Secret заголовок."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        if _has_valid_cron_secret(request):
            return view_func(request, *args, **kwargs)
        return JsonResponse({'status': 'error', 'message': 'Требуется авторизация'}, status=401)
    return wrapper



# ─── Вспомогательные функции ──────────────────────────────────────────────────

# Читающая часть: список прогонов, коды выхода, содержимое логов. Пути,
# замок и сам запуск — в script_runner, здесь только чтение оставленного им.

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
    pattern = os.path.join(script_runner.logs_dir(), f'{script_id}_{script_runner.RUN_ID_GLOB}.log')
    files = sorted(glob.glob(pattern), reverse=True)[:20]
    running_now = script_runner.is_running(script_id)
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
    exit_file = script_runner.exit_file(log_file)
    if not os.path.exists(exit_file):
        return None
    try:
        with open(exit_file) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _get_latest_run(script_id):
    runs = _get_runs(script_id)
    return runs[0] if runs else None


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


# ─── Views ────────────────────────────────────────────────────────────────────

@scripts_auth_basic
def scripts_list(request):
    """GET /api/scripts/ — список скриптов со статусом последнего запуска."""
    result = []
    for script in SCRIPTS_CONFIG:
        sid = script['id']
        latest = _get_latest_run(sid)
        running = script_runner.is_running(sid)
        result.append({
            **{k: script[k] for k in ('id', 'name', 'account', 'schedule', 'description')},
            'topic': script.get('topic', ''),
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
    runs = _get_runs(script_id)
    return JsonResponse({'runs': runs, 'is_running': script_runner.is_running(script_id)})


@scripts_auth_basic
def script_log(request, script_id, run_id):
    """GET /api/scripts/{id}/runs/{run_id}/log/ — содержимое лога.

    Поддерживает ?offset=N для инкрементального polling во время выполнения.
    """
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)

    log_file = script_runner.log_filename(script_id, run_id)
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
    running = is_current_run and script_runner.is_running(script_id)

    return JsonResponse({
        'content': content,
        'offset': new_offset,
        'is_running': running,
        'exit_code': _get_exit_code(log_file),
    })


@scripts_mutation_auth
@require_http_methods(['POST'])
def script_stop(request, script_id):
    """POST /api/scripts/{id}/stop/ — остановить запущенный скрипт."""
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)

    try:
        outcome = script_runner.stop(script_id)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'ok', 'message': script_runner.STOP_MESSAGES[outcome]})


@scripts_mutation_auth
@require_http_methods(['POST'])
def script_run_delete(request, script_id, run_id):
    """POST /api/scripts/{id}/runs/{run_id}/delete/ — удалить лог запуска."""
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)

    # Нельзя удалять лог текущего запуска
    if script_runner.is_running(script_id):
        latest = _get_latest_run(script_id)
        if latest and latest['run_id'] == run_id:
            return JsonResponse({'status': 'error', 'message': 'Нельзя удалить лог запущенного скрипта'}, status=409)

    log_file = script_runner.log_filename(script_id, run_id)
    if not os.path.exists(log_file):
        return JsonResponse({'status': 'error', 'message': 'Лог не найден'}, status=404)

    try:
        os.unlink(log_file)
        for ext in (script_runner.exit_file(log_file), log_file + '.hash'):
            if os.path.exists(ext):
                os.unlink(ext)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'ok'})


@scripts_mutation_auth
@require_http_methods(['POST'])
def script_run_now(request, script_id):
    """POST /api/scripts/{id}/run/ — запустить скрипт немедленно."""
    script = SCRIPTS_BY_ID.get(script_id)
    if not script:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)

    if script_runner.is_running(script_id):
        return JsonResponse({'status': 'error', 'message': 'Скрипт уже запущен'}, status=409)

    if not os.path.exists(script['script']):
        return JsonResponse({
            'status': 'error',
            'message': f'Файл скрипта не найден: {script["script"]}'
        }, status=400)

    run_id = script_runner.launch(script_id)

    return JsonResponse({
        'status': 'ok',
        'run_id': run_id,
        'message': f'Скрипт {script["name"]} запущен',
    })
