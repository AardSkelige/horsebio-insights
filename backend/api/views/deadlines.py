import json
import os
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .scripts_monitor import scripts_auth_basic

DEADLINES_JSON = {
    'horsebio': '/app/moysklad/horsebio/01_daemons/05_payment_deadline/data/deadlines.json',
    'starpony': '/app/moysklad/starpony/01_daemons/02_payment_deadline/data/deadlines.json',
}


def _read_deadlines(account: str) -> dict | None:
    path = DEADLINES_JSON.get(account)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _file_age_hours(account: str) -> float | None:
    path = DEADLINES_JSON.get(account)
    if not path or not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    return (datetime.now().timestamp() - mtime) / 3600


@scripts_auth_basic
@require_http_methods(['GET'])
def get_deadlines(request):
    data = _read_deadlines('horsebio')
    age = _file_age_hours('horsebio')

    if data is None:
        return JsonResponse({'status': 'ok', 'available': False})

    return JsonResponse({
        'status': 'ok',
        'available': True,
        'stale': age is not None and age > 26,
        'age_hours': round(age, 1) if age is not None else None,
        **data,
    })
