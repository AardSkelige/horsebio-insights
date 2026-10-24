import hashlib

from django.db.models import F

from api.services.health_checks import _item_excepted, active_exception_index
from api.services.scripts_registry import HEALTH_CHECK_SCRIPT_ID, SCRIPTS_BY_ID

from .core import CRITICAL, WARNING, Notification, provider

SAMPLE = 3


def _digest(values):
    return hashlib.sha1('|'.join(sorted(values)).encode('utf-8')).hexdigest()[:16]


def _latest_runs():
    from api.models import CheckRunResult

    for script_id in CheckRunResult.objects.filter(script_id__in=list(SCRIPTS_BY_ID)).order_by().values_list('script_id', flat=True).distinct():
        yield CheckRunResult.objects.filter(script_id=script_id).order_by(F('finished_at').desc(nulls_last=True), '-id').first()


def _flagged(category, exc_index):
    kind = category.get('kind')
    fallback = category.get('severity')
    critical, important = [], []
    for item in category.get('items') or []:
        if _item_excepted(kind, item, exc_index):
            continue
        severity = item.get('severity') or fallback
        if severity == 'critical':
            critical.append(item)
        elif severity == 'important':
            important.append(item)
    return critical, important


def _line(item):
    return ' — '.join(part for part in (item.get('object'), item.get('detail')) if part)


@provider('checks')
def check_notifications():
    exc_index = active_exception_index()
    for run in _latest_runs():
        script = SCRIPTS_BY_ID[run.script_id]
        name = script['name']
        route = f'/checks/{run.script_id}'
        if run.exit_code not in (0, None):
            yield Notification(
                key=f'checks:{run.script_id}:failed',
                level=CRITICAL,
                title=f'Проверка «{name}» не отработала',
                body=f'Последний запуск завершился с кодом {run.exit_code}',
                action='Откройте журнал проверки и посмотрите, на чём она остановилась.',
                fingerprint='failed',
                route=route,
            )
            continue
        for category in run.findings or []:
            if run.script_id == HEALTH_CHECK_SCRIPT_ID and category.get('key') == 'pending_returns':
                continue
            critical, important = _flagged(category, exc_index)
            items = critical or important
            if not items:
                continue
            yield Notification(
                key=f'checks:{run.script_id}:{category.get("key") or category.get("title")}',
                level=CRITICAL if critical else WARNING,
                title=f'{name}: {category.get("title") or "находки"} — {len(items)}',
                body='; '.join(_line(item) for item in items[:SAMPLE]),
                action='Разберите на странице проверки.',
                fingerprint=_digest(item.get('ms_id') or item.get('key') or _line(item) for item in items),
                links=[(item['object'], item['ms_href']) for item in items[:SAMPLE] if item.get('ms_href') and item.get('object')],
                route=route,
            )
