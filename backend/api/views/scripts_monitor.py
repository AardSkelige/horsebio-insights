# api/views/scripts_monitor.py
"""
Чтение того, что оставили после себя прогоны проверок: история, коды выхода,
логи — и авторизация страницы «Проверки».

Своих ручек здесь больше нет. Их было шесть (/api/scripts/…), они дублировали
/api/checks/scripts/… и к 10.09.2026 не звал их никто: страница ходит в checks,
cron — в `manage.py run_check`. Дублирующая поверхность вдобавок отставала:
чтение в ней осталось открытым любому вошедшему, когда «Проверки» уже стали
суперюзерскими. Удалена; вьюхи живут в api/views/checks.py, они и зовут
здешних помощников и декораторы.

Сам запуск живёт в api/services/script_runner.py и идёт отдельным процессом
(`manage.py run_check`). Реестр задач — в api/services/scripts_registry.py.
"""
import os
import re
import glob
import hashlib
from datetime import datetime
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect

from api.services import script_runner

import logging
logger = logging.getLogger(__name__)


# ─── Авторизация ──────────────────────────────────────────────────────────────
#
# Machine-to-machine входа здесь больше нет. Он был нужен, пока запуск шёл
# по HTTP: cron дёргал /api/scripts/<id>/run/ с заголовком X-Cron-Secret,
# а секрет лежал в crontab открытым текстом. С переездом на `manage.py
# run_check` запуск идёт мимо HTTP, и авторизация теперь — это доступ
# к серверу. Забытый секрет — это лишний вход в систему, который никто
# не сторожит.
#
# Чтение 10.09.2026 приравнено к записи: было «любой вошедший», стало
# «суперпользователь». Открытым оно осталось с тех времён, когда «Проверки»
# видели все; страница давно суперюзерская, а в логах прогонов лежат номера
# документов, цены и контрагенты. Заодно снято исключение в PUBLIC_PATHS —
# теперь до этих путей доходят и постраничные права (страница `checks`).

def scripts_auth(view_func):
    """Только суперпользователь."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        status = 403 if request.user.is_authenticated else 401
        return JsonResponse({'status': 'error', 'message': 'Нет доступа'}, status=status)
    return wrapper


def scripts_mutation_auth(view_func):
    """Изменения: суперпользователь, CSRF обязателен."""
    csrf_protected_view = csrf_protect(view_func)

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return csrf_protected_view(request, *args, **kwargs)
        status = 403 if request.user.is_authenticated else 401
        return JsonResponse({'status': 'error', 'message': 'Нет доступа'}, status=status)

    # Глобальный middleware пропускает wrapper, а ветка сессии выше явно
    # прогоняется через csrf_protect. Без этого запрос без токена получал бы
    # от middleware страницу CSRF вместо внятного «Нет доступа».
    return csrf_exempt(wrapper)


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
