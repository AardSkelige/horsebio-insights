import base64
import binascii
import json
import os
from datetime import date, datetime, timedelta

import requests
from django.db import transaction
from django.utils import timezone

from api.services import http_retry
from production_plan.models import WbOrder, WbSync
from production_plan.services.articles import normalize

URL = 'https://statistics-api.wildberries.ru/api/v1/supplier/orders'
TIMEOUT = 60
HISTORY_DAYS = 89
PAGE = 80000
NIGHT_PAUSES = (60, 60, 60)
QUICK_PAUSES = (1, 2, 3)


class WbSalesError(Exception):
    pass


def configured():
    return bool(os.getenv('WB_STATS_TOKEN'))


def _get(date_from, pauses):
    return http_retry.send(
        lambda: requests.get(URL, headers={'Authorization': os.getenv('WB_STATS_TOKEN')}, params={'dateFrom': date_from}, timeout=TIMEOUT),
        pauses,
        lambda exc: WbSalesError(f'WB недоступен: {exc}'),
        lambda response: WbSalesError(f'WB ответил {response.status_code}: {response.text[:300]}'),
    ).json()


def _order(row):
    return WbOrder(
        srid=row['srid'],
        date=timezone.make_aware(datetime.fromisoformat(row['date'])),
        article=normalize(row['supplierArticle']),
        is_cancel=bool(row.get('isCancel')),
    )


def sync(today, pauses=NIGHT_PAUSES):
    start = today - timedelta(days=HISTORY_DAYS)
    date_from, total = start.isoformat(), 0
    while True:
        rows = _get(date_from, pauses)
        if not isinstance(rows, list):
            raise WbSalesError('WB прислал неожиданный ответ')
        if not rows:
            break
        WbOrder.objects.bulk_create(
            list({row['srid']: _order(row) for row in rows}.values()),
            update_conflicts=True, unique_fields=['srid'], update_fields=['date', 'article', 'is_cancel'],
        )
        total += len(rows)
        if len(rows) < PAGE or rows[-1]['lastChangeDate'] == date_from:
            break
        date_from = rows[-1]['lastChangeDate']
    with transaction.atomic():
        state = WbSync.objects.select_for_update().first()
        if state is None:
            WbSync.objects.create(covered_from=start)
        else:
            gap = timezone.localdate(state.synced_at) < start
            state.covered_from = start if gap else min(state.covered_from, start)
            state.save()
    return total


def state():
    return WbSync.objects.first()


def covered_from():
    current = state()
    return current.covered_from if current else None


def expires():
    parts = (os.getenv('WB_STATS_TOKEN') or '').split('.')
    if len(parts) != 3:
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
        return date.fromtimestamp(claims['exp'])
    except (ValueError, KeyError, TypeError, binascii.Error):
        return None
