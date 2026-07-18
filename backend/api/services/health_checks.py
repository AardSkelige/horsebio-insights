# api/services/health_checks.py
"""
Сервис проверки здоровья себестоимости (health_check) для страницы /checks.

Источник истины по исключениям — БД (модель HealthCheckException). Скрипт
01_health_check.py читает исключения из data/*.json и сам в БД не ходит, поэтому
перед каждым запуском бэкенд экспортирует исключения из БД в те же JSON-файлы
(export_exceptions_to_json). Результаты скрипт пишет в <run>.results.json, которые
бэкенд разбирает в CheckRunResult (ingest_results_file).
"""
import os
import json
import logging
from collections import defaultdict

from django.conf import settings

logger = logging.getLogger(__name__)

# Файлы исключений по типу (хранятся как {acknowledged: [{doc_id, ...}]})
ACK_FILES = {
    'enters':       'enters_acknowledged.json',
    'losses':       'losses_acknowledged.json',
    'inventories':  'inventories_acknowledged.json',
    'moves':        'moves_acknowledged.json',
    'supplies':     'supplies_acknowledged.json',
    'salesreturns': 'salesreturns_acknowledged.json',
    'enter_zero':   'enter_zero_acknowledged.json',
}
DEVIATIONS_FILE = 'avg_deviations_ignore.json'
SUPPLY_JUMPS_FILE = 'supply_jumps_ignore.json'

ACK_COMMENTS = {
    'enters':       'Оприходования на внутренних складах — проверены и подтверждены. Документ не будет появляться в отчёте.',
    'losses':       'Списания — проверены и подтверждены. Документ не будет появляться в отчёте.',
    'inventories':  'Инвентаризации — проверены и подтверждены. Документ не будет появляться в отчёте.',
    'moves':        'Перемещения — проверены и подтверждены. Документ не будет появляться в отчёте.',
    'supplies':     'Приёмки — проверены и подтверждены. doc_id = UUID документа в МойСклад.',
    'salesreturns': 'Возвраты от покупателей — проверены и подтверждены. Документ не будет появляться в отчёте.',
    'enter_zero':   'Оприходования с нулевой ценой — проверены и подтверждены.',
}


def _data_dir():
    override = getattr(settings, 'HEALTH_CHECK_DATA_DIR', None)
    if override:
        return str(override)
    return os.path.join(str(settings.BASE_DIR), 'moysklad', 'horsebio',
                        '02_checks', '01_health', 'data')


def _read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Очистка отработавших исключений ──────────────────────────────────────────

# Документные проверки сканируют последние 3 месяца (doc_months/enter_months=3).
# Исключение по документу старше этого окна больше никогда не сработает — документ
# в отчёт не попадает. 4 месяца = окно + месяц запаса.
EXPIRE_DAYS = 120


def cleanup_expired_exceptions():
    """Удалить документные исключения, чей документ гарантированно вышел из окна
    сканирования. deviations и supply_jumps бессрочные — не трогаются.
    Возвращает число удалённых записей."""
    from datetime import timedelta
    from django.utils import timezone
    from api.models import HealthCheckException

    cutoff = timezone.now() - timedelta(days=EXPIRE_DAYS)
    qs = HealthCheckException.objects.filter(
        kind__in=HealthCheckException.ACK_KINDS, created_at__lt=cutoff)
    expired = list(qs)
    if not expired:
        return 0
    for r in expired:
        logger.info('Удалено отработавшее исключение %s:%s %s (создано %s): %s',
                    r.kind, r.key, r.label, r.created_at.date(), r.reason[:80])
    qs.delete()
    logger.info('Очистка исключений health_check: удалено %d отработавших', len(expired))
    return len(expired)


# ─── Экспорт исключений из БД в data/*.json (перед запуском скрипта) ───────────

def export_exceptions_to_json(data_dir=None):
    """Перезаписать data/*.json содержимым из БД. Вызывается перед запуском health_check."""
    from api.models import HealthCheckException

    data_dir = data_dir or _data_dir()
    os.makedirs(data_dir, exist_ok=True)

    by_kind = defaultdict(list)
    for r in HealthCheckException.objects.all():
        by_kind[r.kind].append(r)

    # Acknowledged-типы
    for kind, fname in ACK_FILES.items():
        items = []
        for r in by_kind.get(kind, []):
            entry = {'doc_id': r.key, 'doc_name': r.label, 'reason': r.reason}
            if isinstance(r.extra, dict):
                for k, v in r.extra.items():
                    entry.setdefault(k, v)
            items.append(entry)
        _write_json(os.path.join(data_dir, fname),
                    {'_comment': ACK_COMMENTS.get(kind, ''), 'acknowledged': items})

    # Отклонения FIFO (notes-dict по product_code)
    notes = {}
    for r in by_kind.get('deviations', []):
        extra = r.extra if isinstance(r.extra, dict) else {}
        notes[r.key] = {
            'checked': extra.get('checked', ''),
            'status': extra.get('status', 'норма'),
            'note': r.reason,
        }
    _write_json(os.path.join(data_dir, DEVIATIONS_FILE), {
        '_comment': 'Объяснения отклонений FIFO vs приёмка. Позиции продолжают выводиться в отчёте, но со статусом и пояснением.',
        '_format': 'notes — dict: product_code -> {checked, status (норма|ошибка|исправлено), note}',
        'notes': notes,
    })

    # Скачки цен (ignored-list по name). supply_doc в extra — разовое исключение:
    # глушит только скачок этой приёмки; без него — вечное («у товара всегда так»)
    ignored = []
    for r in by_kind.get('supply_jumps', []):
        entry = {'name': r.key, 'reason': r.reason}
        supply_doc = (r.extra or {}).get('supply_doc')
        if supply_doc:
            entry['supply_doc'] = supply_doc
        ignored.append(entry)
    _write_json(os.path.join(data_dir, SUPPLY_JUMPS_FILE), {
        '_comment': 'Позиции исключённые из проверки скачков цен в приёмках. Добавляй сюда когда скачок объяснён и не требует внимания.',
        'ignored': ignored,
    })

    logger.info('Экспортировано исключений health_check в %s', data_dir)


# ─── Импорт исключений из data/*.json в БД (сид-миграция) ──────────────────────

def import_exceptions_from_files(model_cls, data_dir=None):
    """Заполнить модель исключений из существующих data/*.json. Идемпотентно.

    model_cls передаётся явно, чтобы можно было вызвать из data-миграции
    (apps.get_model). Возвращает число созданных записей.
    """
    data_dir = data_dir or _data_dir()
    created = 0

    for kind, fname in ACK_FILES.items():
        data = _read_json(os.path.join(data_dir, fname))
        for entry in data.get('acknowledged', []):
            doc_id = entry.get('doc_id')
            if not doc_id:
                continue
            extra = {k: v for k, v in entry.items()
                     if k not in ('doc_id', 'doc_name', 'reason')}
            _, was_created = model_cls.objects.get_or_create(
                kind=kind, key=doc_id,
                defaults={'label': entry.get('doc_name', '') or '',
                          'reason': entry.get('reason', '') or '',
                          'extra': extra},
            )
            created += int(was_created)

    data = _read_json(os.path.join(data_dir, DEVIATIONS_FILE))
    for code, note in data.get('notes', {}).items():
        if not code:
            continue
        extra = {'status': note.get('status', ''), 'checked': note.get('checked', '')}
        _, was_created = model_cls.objects.get_or_create(
            kind='deviations', key=code,
            defaults={'label': code, 'reason': note.get('note', '') or '', 'extra': extra},
        )
        created += int(was_created)

    data = _read_json(os.path.join(data_dir, SUPPLY_JUMPS_FILE))
    for entry in data.get('ignored', []):
        name = entry.get('name')
        if not name:
            continue
        _, was_created = model_cls.objects.get_or_create(
            kind='supply_jumps', key=name,
            defaults={'label': name, 'reason': entry.get('reason', '') or ''},
        )
        created += int(was_created)

    return created


# ─── Разбор результатов скрипта в БД ──────────────────────────────────────────

HEALTH_SCRIPT_ID = 'horsebio_health_check'

# Статусы deviations с конечным жизненным циклом: проблема закрыта, запись нужна
# только пока отклонение ещё видно в отчёте. «норма» — постоянное свойство товара,
# не чистится: отклонение может уйти и вернуться, объяснение снова пригодится.
_RESOLVED_DEVIATION_STATUSES = ('исправлено', 'ошибка-некритично')


def cleanup_resolved_deviations(categories):
    """Удалить deviations-исключения со статусом «исправлено»/«ошибка-некритично»,
    чьи позиции больше не фигурируют в отчёте — отклонение реально рассосалось.
    Возвращает число удалённых записей."""
    from api.models import HealthCheckException

    still_flagged = {
        it.get('key')
        for cat in categories if cat.get('kind') == 'deviations'
        for it in cat.get('items', [])
    }
    qs = HealthCheckException.objects.filter(
        kind='deviations', extra__status__in=_RESOLVED_DEVIATION_STATUSES,
    ).exclude(key__in=still_flagged)
    resolved = list(qs)
    for r in resolved:
        logger.info('Удалено закрытое deviations-исключение %s %s (%s): %s',
                    r.key, r.label, (r.extra or {}).get('status'), r.reason[:80])
    qs.delete()
    return len(resolved)


def ingest_results_file(script_id, run_id, path, exit_code=None, duration_sec=None):
    """Разобрать <run>.results.json и сохранить снимок в CheckRunResult."""
    from django.utils import timezone
    from api.models import CheckRunResult

    data = _read_json(path)
    if not data:
        return None

    obj, _ = CheckRunResult.objects.update_or_create(
        script_id=script_id, run_id=run_id,
        defaults={
            'summary': data.get('summary', {}),
            'findings': data.get('categories', []),
            'exit_code': exit_code,
            'duration_sec': duration_sec,
            'finished_at': timezone.now(),
        },
    )
    # Успешный запуск хелс-чека — закрытые и рассосавшиеся отклонения больше не нужны
    if script_id == HEALTH_SCRIPT_ID and exit_code == 0:
        try:
            cleanup_resolved_deviations(data.get('categories', []))
        except Exception:
            logger.exception('Не удалось почистить закрытые deviations-исключения')
    return obj
