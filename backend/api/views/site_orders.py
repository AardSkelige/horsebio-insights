import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .scripts_monitor import scripts_auth

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio', '_shared'))
from order_email_utils import build_customer_name, state_lock, load_state, save_state  # noqa: E402 — те же helper'ы, что и в 02_create_orders.py

logger = logging.getLogger(__name__)

# Тот же путь, что и в SCRIPTS_CONFIG (scripts_monitor.py) — контейнер бэкенда
# всегда монтирует backend/ в /app, локально и в проде (см. docker-compose*.yml)
STATE_FILE = Path('/app/moysklad/horsebio/01_daemons/06_order_email_sync/data/.order_email_state.json')

MOYSKLAD_ORDER_URL = 'https://online.moysklad.ru/app/#customerorder/edit?id={}'

STATUS_LABELS = {
    'error': 'Ошибка создания',
    'cancelled': 'Отменён — не оплачен',
    'paid': 'Оплачен и заведён',
    'waiting_payment': 'Ждёт оплаты',
    'processing': 'В обработке',
}

SORT_KEYS = {
    'name': lambda r: r['name'] or '',
    'date': lambda r: r['date'] or '',
    'sum': lambda r: r['sum'],
    'status': lambda r: r['status'],
}


def _parse_dt(value):
    """Время в state бывает в двух форматах: 'YYYY-MM-DD HH:MM:SS' (из письма,
    см. HB_ORDER_DATA) или ISO с микросекундами (datetime.isoformat() из ms-полей,
    которые пишет 02_create_orders.py)."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _fmt(dt):
    return dt.strftime('%d.%m %H:%M') if dt else None


def _compute_status(ms):
    if ms.get('last_error'):
        return 'error'
    if ms.get('cancelled_at'):
        return 'cancelled'
    if ms.get('payment_id') or ms.get('paid_externally'):
        return 'paid'
    if ms.get('customerorder_id'):
        return 'waiting_payment'
    return 'processing'


def _build_timeline(order, ms):
    """Хронология для тултипа на странице — из истории писем + меток ms."""
    history = order.get('history') or []
    events = []

    if history:
        first = history[0]
        events.append((_parse_dt(first.get('created')) or _parse_dt(first.get('fetched_at')), 'Письмо получено'))

        was_paid = bool(first.get('paid'))
        for snap in history[1:]:
            is_paid = bool(snap.get('paid'))
            if is_paid and not was_paid:
                events.append((_parse_dt(snap.get('modified')) or _parse_dt(snap.get('fetched_at')), 'Оплата получена'))
            was_paid = is_paid

    created_at = _parse_dt(ms.get('created_at'))
    if created_at:
        name = ms.get('customerorder_name')
        events.append((created_at, f'Черновик №{name} создан в МойСклад' if name else 'Черновик создан в МойСклад'))

    last_error_at = _parse_dt(ms.get('last_error_at'))
    if last_error_at and ms.get('last_error'):
        events.append((last_error_at, f'Ошибка: {ms["last_error"]}'))

    cancelled_at = _parse_dt(ms.get('cancelled_at'))
    if cancelled_at:
        events.append((cancelled_at, ms.get('cancel_reason') or 'Черновик отменён'))

    paid_at = _parse_dt(ms.get('paid_at'))
    if paid_at:
        if ms.get('paid_externally'):
            events.append((paid_at, 'Оплата обработана сотрудником вручную в МойСклад'))
        elif ms.get('payment_name'):
            events.append((paid_at, f'Заказ проведён, платёж №{ms["payment_name"]} создан'))
        else:
            events.append((paid_at, 'Заказ проведён'))

    events = [(dt, text) for dt, text in events if dt]
    events.sort(key=lambda e: e[0])
    return [{'time': _fmt(dt), 'text': text} for dt, text in events]


def _build_row(order_id, order):
    """Без timeline — timeline считается только для итоговой страницы после
    пагинации (см. site_orders_list), чтобы не тратить работу на заказы,
    которые пользователь всё равно не увидит."""
    latest = order.get('latest') or {}
    ms = order.get('ms') or {}
    history = order.get('history') or []

    order_dt = _parse_dt(latest.get('created'))
    if order_dt is None and history:
        order_dt = _parse_dt(history[0].get('fetched_at'))

    status = _compute_status(ms)

    return {
        'order_id': order_id,
        'number': latest.get('number'),
        'name': build_customer_name(latest) or '—',
        'phone': (latest.get('field') or {}).get('phone', ''),
        'date': order_dt.isoformat() if order_dt else None,
        'date_label': _fmt(order_dt),
        'sum': float(latest.get('total') or 0),
        'status': status,
        'status_label': STATUS_LABELS.get(status, status),
        'error_text': ms.get('last_error') if status == 'error' else None,
        'cancel_text': ms.get('cancel_reason') if status == 'cancelled' else None,
        'site_link': latest.get('order_link') or None,
        'ms_link': MOYSKLAD_ORDER_URL.format(ms['customerorder_id']) if ms.get('customerorder_id') else None,
    }


@api_view(['GET'])
def site_orders_list(request):
    """
    Список заказов сайта (horse-bio.ru) и их состояние в МойСклад — читает
    state-файл, который пишут 01_read_order_emails.py / 02_create_orders.py.

    ?search=       — по имени/телефону/номеру заказа (регистронезависимо)
    ?date_from=    — YYYY-MM-DD, включительно
    ?date_to=      — YYYY-MM-DD, включительно
    ?sort=         — name|date|sum|status (по умолчанию date)
    ?dir=          — asc|desc (по умолчанию desc)
    ?limit=&offset= — пагинация (по умолчанию limit=20)
    """
    if not STATE_FILE.exists():
        return Response({
            'status': 'no_data',
            'message': 'Демон чтения почты ещё ни разу не запускался — данных пока нет.',
        })

    try:
        state = json.loads(STATE_FILE.read_text())
    except Exception as e:
        logger.exception('Не удалось прочитать state-файл заказов сайта')
        return Response({'status': 'error', 'message': str(e)}, status=500)

    orders_by_id = {}
    rows = []
    for order_id, order in state.get('orders', {}).items():
        if not order.get('latest'):
            continue
        try:
            rows.append(_build_row(order_id, order))
            orders_by_id[order_id] = order
        except Exception:
            # Одна повреждённая запись не должна ронять всю страницу целиком —
            # пропускаем её и логируем, остальные заказы показываем как обычно
            logger.exception('Не удалось построить строку для заказа %s — пропускаю', order_id)

    search = request.GET.get('search', '').strip().lower()
    if search:
        def matches(r):
            haystack = ' '.join(str(x) for x in (r['name'], r['phone'], r['number'], r['order_id']) if x).lower()
            return search in haystack
        rows = [r for r in rows if matches(r)]

    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    if date_from:
        rows = [r for r in rows if r['date'] and r['date'][:10] >= date_from]
    if date_to:
        rows = [r for r in rows if r['date'] and r['date'][:10] <= date_to]

    sort_key = SORT_KEYS.get(request.GET.get('sort', 'date'), SORT_KEYS['date'])
    rows.sort(key=sort_key, reverse=(request.GET.get('dir', 'desc') != 'asc'))

    total = len(rows)
    try:
        limit = max(1, min(int(request.GET.get('limit', 20)), 200))
        offset = max(0, int(request.GET.get('offset', 0)))
    except ValueError:
        limit, offset = 20, 0

    page = rows[offset:offset + limit]
    for row in page:
        row['timeline'] = _build_timeline(orders_by_id[row['order_id']], orders_by_id[row['order_id']].get('ms') or {})

    last_checked = datetime.fromtimestamp(STATE_FILE.stat().st_mtime).isoformat()

    return Response({
        'status': 'success',
        'data': {
            'rows': page,
            'total': total,
            'last_checked': last_checked,
        },
    })


@scripts_auth
@api_view(['DELETE'])
def site_order_delete(request, order_id):
    """
    DELETE /api/site-orders/{order_id}/ — убрать заказ из журнала автоматизации
    (используется кнопкой «Удалить» на находках /checks и на странице «Заказы
    сайта» — для тестовых/ошибочных записей). Само письмо в почте и документы
    в МойСклад не трогает — только внутренний state-файл. Убираем заодно
    Message-ID письма(-ем) этого заказа из processed_message_ids, чтобы при
    следующей проверке почты письмо могло быть разобрано заново.
    """
    if not STATE_FILE.exists():
        return Response({'status': 'error', 'message': 'Файл состояния не найден'}, status=404)

    # Тот же лок, что держат 01_read_order_emails.py / 02_create_orders.py: без него
    # это read-modify-write гонится с демонами и молча затирает только что созданный
    # ими заказ (см. state_lock() и инцидент с заказом 532598916 в order_email_utils.py)
    try:
        with state_lock(STATE_FILE):
            state = load_state(STATE_FILE, {})

            order = state.get('orders', {}).pop(order_id, None)
            if order is None:
                return Response({'status': 'error', 'message': 'Заказ не найден в журнале'}, status=404)

            processed = state.get('processed_message_ids', [])
            for snap in order.get('history', []):
                mid = snap.get('message_id')
                if mid in processed:
                    processed.remove(mid)

            save_state(STATE_FILE, state)
    except Exception as e:
        logger.exception('Не удалось удалить заказ %s из state-файла', order_id)
        return Response({'status': 'error', 'message': str(e)}, status=500)

    return Response({'status': 'success'})
