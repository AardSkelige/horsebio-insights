# api/views/checks.py
"""
API страницы /checks — дашборд результатов проверок и управление исключениями.

Переиспользует запуск/историю/логи из scripts_monitor. Для health_check добавляет
структурированные результаты (CheckRunResult) и CRUD исключений (HealthCheckException).
"""
import os
import json
import signal
import time
from collections import defaultdict

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from api.models import HealthCheckException, CheckRunResult
from .scripts_monitor import (
    SCRIPTS_CONFIG, SCRIPTS_BY_ID, HEALTH_CHECK_SCRIPT_ID,
    scripts_auth, scripts_auth_basic, _starpony_access_denied,
    _get_runs, _get_latest_run, _is_running, _run_script_async,
    _log_filename, _process_terminal_output, _get_exit_code,
    _pid_file, _pid_is_alive, _exit_file,
)

_KIND_LABELS = dict(HealthCheckException.KIND_CHOICES)
_SEVERITY_RANK = {'critical': 3, 'important': 2, 'warning': 1, 'info': 0}


# ─── Вспомогательные ──────────────────────────────────────────────────────────

def _is_superuser(request):
    return request.user.is_authenticated and request.user.is_superuser


def _findings_identity(findings):
    """Множество идентичностей находок запуска — для определения «изменилось»."""
    ids = set()
    for cat in findings or []:
        ckey = cat.get('key', '')
        for it in cat.get('items', []):
            ids.add(f"{ckey}|{it.get('key') or it.get('object', '')}")
    return ids


def _serialize_health_run(r, prev):
    """Сериализовать CheckRunResult с дельтой относительно предыдущего запуска."""
    summary = r.summary or {}
    out = {
        'run_id': r.run_id,
        'finished_at': r.finished_at.strftime('%Y-%m-%d %H:%M:%S') if r.finished_at else '',
        'exit_code': r.exit_code,
        'duration_sec': r.duration_sec,
        'summary': {k: summary.get(k, 0) for k in ('critical', 'important', 'warnings', 'ok')},
    }
    if prev is not None:
        prev_sum = prev.summary or {}
        out['delta'] = {
            k: (summary.get(k, 0) - prev_sum.get(k, 0))
            for k in ('critical', 'important', 'warnings')
        }
        out['changed'] = _findings_identity(r.findings) != _findings_identity(prev.findings)
    else:
        out['delta'] = None
        out['changed'] = True
    return out


def _serialize_exception(e):
    return {
        'id': e.id,
        'kind': e.kind,
        'kind_label': _KIND_LABELS.get(e.kind, e.kind),
        'key': e.key,
        'label': e.label,
        'reason': e.reason,
        'extra': e.extra or {},
        'created_at': e.created_at.strftime('%Y-%m-%d %H:%M') if e.created_at else '',
        'created_by': e.created_by.username if e.created_by else None,
    }


# ─── Обзор и история ──────────────────────────────────────────────────────────

@scripts_auth
def checks_overview(request):
    """GET /api/checks/scripts/ — обзор всех скриптов со сводкой."""
    superuser = _is_superuser(request)
    latest_results = {}
    for s in SCRIPTS_CONFIG:
        if s.get('structured'):
            crr = CheckRunResult.objects.filter(script_id=s['id']).order_by('-finished_at').first()
            if crr:
                latest_results[s['id']] = crr
    result = []
    for script in SCRIPTS_CONFIG:
        sid = script['id']
        if script.get('hidden'):
            continue
        if script.get('account') == 'StarPony' and not superuser:
            continue
        item = {
            **{k: script[k] for k in ('id', 'name', 'account', 'schedule', 'description')},
            'topic': script.get('topic', ''),
            'structured': bool(script.get('structured')),
            'is_health': sid == HEALTH_CHECK_SCRIPT_ID,
            'is_running': _is_running(sid),
            'last_run': _get_latest_run(sid),
            'script_exists': os.path.exists(script['script']),
        }
        if script.get('structured'):
            crr = latest_results.get(sid)
            item['summary'] = (crr.summary or {}) if crr else None
            item['last_result_run_id'] = crr.run_id if crr else None
        result.append(item)
    return JsonResponse({'scripts': result})


@scripts_auth
def checks_runs(request, script_id):
    """GET /api/checks/scripts/{id}/runs/ — история запусков."""
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied

    if SCRIPTS_BY_ID.get(script_id, {}).get('structured'):
        rows = list(CheckRunResult.objects.filter(script_id=script_id).order_by('-finished_at')[:30])
        runs = [_serialize_health_run(r, rows[i + 1] if i + 1 < len(rows) else None)
                for i, r in enumerate(rows)]
        return JsonResponse({'kind': 'structured', 'runs': runs, 'is_running': _is_running(script_id)})

    return JsonResponse({'kind': 'log', 'runs': _get_runs(script_id), 'is_running': _is_running(script_id)})


@scripts_auth
def checks_results(request, script_id):
    """GET /api/checks/scripts/{id}/results/?run_id= — структурированные находки."""
    if not SCRIPTS_BY_ID.get(script_id, {}).get('structured'):
        return JsonResponse({'status': 'error', 'message': 'У скрипта нет структурированных результатов'}, status=400)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied

    run_id = request.GET.get('run_id')
    qs = CheckRunResult.objects.filter(script_id=script_id)
    crr = qs.filter(run_id=run_id).first() if run_id else qs.order_by('-finished_at').first()
    if not crr:
        return JsonResponse({'results': None})

    # Активные исключения — только у health_check. exception_keys — ключи по типам;
    # exceptions_map — причина и привязка к приёмке (для «прошлого разбора» в находках)
    exc_keys = defaultdict(list)
    exc_map = defaultdict(dict)
    if script_id == HEALTH_CHECK_SCRIPT_ID:
        for kind, key, reason, extra in HealthCheckException.objects.values_list(
                'kind', 'key', 'reason', 'extra'):
            exc_keys[kind].append(key)
            exc_map[kind][key] = {
                'reason': reason,
                'supply_doc': (extra or {}).get('supply_doc', ''),
            }

    return JsonResponse({
        'results': {
            'run_id': crr.run_id,
            'finished_at': crr.finished_at.strftime('%Y-%m-%d %H:%M:%S') if crr.finished_at else '',
            'duration_sec': crr.duration_sec,
            'summary': crr.summary or {},
            'categories': crr.findings or [],
            'exception_keys': exc_keys,
            'exceptions_map': exc_map,
        }
    })


@scripts_auth
def checks_log(request, script_id):
    """GET /api/checks/scripts/{id}/log/?run_id= — сырой лог (для 6 скриптов и отладки)."""
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied

    run_id = request.GET.get('run_id')
    if not run_id:
        latest = _get_latest_run(script_id)
        run_id = latest['run_id'] if latest else None
    if not run_id:
        return JsonResponse({'content': '', 'is_running': False, 'exit_code': None, 'run_id': None})

    log_file = _log_filename(script_id, run_id)
    if not os.path.exists(log_file):
        return JsonResponse({'content': '', 'is_running': False, 'exit_code': None, 'run_id': run_id})

    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace', newline='') as f:
            content = _process_terminal_output(f.read())
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    latest = _get_latest_run(script_id)
    running = bool(latest and latest['run_id'] == run_id and _is_running(script_id))
    return JsonResponse({
        'content': content,
        'run_id': run_id,
        'is_running': running,
        'exit_code': _get_exit_code(log_file),
    })


# ─── Запуск / остановка ───────────────────────────────────────────────────────

@csrf_exempt
@scripts_auth
@require_http_methods(['POST'])
def checks_run(request, script_id):
    """POST /api/checks/scripts/{id}/run/ — запустить скрипт."""
    script = SCRIPTS_BY_ID.get(script_id)
    if not script:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied
    if _is_running(script_id):
        return JsonResponse({'status': 'error', 'message': 'Скрипт уже запущен'}, status=409)
    if not os.path.exists(script['script']):
        return JsonResponse({'status': 'error', 'message': f'Файл скрипта не найден: {script["script"]}'}, status=400)

    run_id = _run_script_async(script_id, script['script'], script['args'])
    return JsonResponse({'status': 'ok', 'run_id': run_id, 'message': f'Скрипт {script["name"]} запущен'})


@csrf_exempt
@scripts_auth
@require_http_methods(['POST'])
def checks_stop(request, script_id):
    """POST /api/checks/scripts/{id}/stop/ — остановить скрипт."""
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
        if pgid is not None:
            os.killpg(pgid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
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
@scripts_auth
@require_http_methods(['DELETE'])
def checks_run_delete(request, script_id, run_id):
    """DELETE /api/checks/scripts/{id}/runs/{run_id}/ — удалить запуск из истории."""
    if script_id not in SCRIPTS_BY_ID:
        return JsonResponse({'status': 'error', 'message': 'Скрипт не найден'}, status=404)
    denied = _starpony_access_denied(request, script_id)
    if denied:
        return denied

    if _is_running(script_id):
        latest = _get_latest_run(script_id)
        if latest and latest['run_id'] == run_id:
            return JsonResponse({'status': 'error', 'message': 'Нельзя удалить текущий запуск'}, status=409)

    deleted = CheckRunResult.objects.filter(script_id=script_id, run_id=run_id).delete()[0]

    log_file = _log_filename(script_id, run_id)
    for path in (log_file, _exit_file(log_file), log_file + '.hash'):
        if os.path.exists(path):
            try:
                os.unlink(path)
                deleted += 1
            except OSError:
                pass

    if not deleted:
        return JsonResponse({'status': 'error', 'message': 'Запуск не найден'}, status=404)
    return JsonResponse({'status': 'ok'})


# ─── Исключения (CRUD) ────────────────────────────────────────────────────────

@csrf_exempt
@scripts_auth
@require_http_methods(['GET', 'POST'])
def checks_exceptions(request):
    """GET /api/checks/exceptions/?kind= — список; POST — добавить."""
    if request.method == 'GET':
        qs = HealthCheckException.objects.all()
        kind = request.GET.get('kind')
        if kind:
            qs = qs.filter(kind=kind)
        return JsonResponse({'exceptions': [_serialize_exception(e) for e in qs]})

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Некорректный JSON'}, status=400)

    kind = data.get('kind')
    key = (data.get('key') or '').strip()
    if kind not in _KIND_LABELS:
        return JsonResponse({'status': 'error', 'message': 'Неизвестный тип исключения'}, status=400)
    if not key:
        return JsonResponse({'status': 'error', 'message': 'Не указан ключ находки (key)'}, status=400)

    extra = data.get('extra') or {}
    if kind == HealthCheckException.KIND_DEVIATIONS and 'status' not in extra:
        extra['status'] = 'норма'

    obj, created = HealthCheckException.objects.update_or_create(
        kind=kind, key=key,
        defaults={
            'label': data.get('label', '') or '',
            'reason': data.get('reason', '') or '',
            'extra': extra,
            'created_by': request.user if request.user.is_authenticated else None,
        },
    )
    return JsonResponse({'exception': _serialize_exception(obj), 'created': created},
                        status=201 if created else 200)


@csrf_exempt
@scripts_auth
@require_http_methods(['PATCH', 'DELETE'])
def checks_exception_detail(request, exc_id):
    """PATCH /api/checks/exceptions/{id}/ — изменить причину; DELETE — убрать."""
    try:
        exc = HealthCheckException.objects.get(id=exc_id)
    except HealthCheckException.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Исключение не найдено'}, status=404)

    if request.method == 'DELETE':
        exc.delete()
        return JsonResponse({'status': 'ok'})

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Некорректный JSON'}, status=400)

    if 'reason' in data:
        exc.reason = data.get('reason', '') or ''
    if 'extra' in data and isinstance(data['extra'], dict):
        exc.extra = {**(exc.extra or {}), **data['extra']}
    exc.save()
    return JsonResponse({'exception': _serialize_exception(exc)})
