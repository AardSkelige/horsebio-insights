"""Поиск дублей в МойСклад по заказам Ozon Доставки.

На одну покупку получается два документа: наш — заведённый по письму сайта (там
покупатель, оплата и полная сумма) и чужой — созданный синхронизацией
МойСклад ↔ Ozon по отправлению (контрагент «Озон», сумма без доставки, без
оплаты). Второй мешает учёту, но полезное в нём есть: номер отправления, дата
отгрузки, статус от Ozon.

Модуль только читает и сравнивает. Ничего не удаляет и не правит: сначала надо
посмотреть на живых данных, что находится, и понять, не пересоздаст ли
синхронизация удалённый документ.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from msapi import http as ms_http
from ozon_logistics.models import OzonPosting

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

BASE = 'https://api.moysklad.ru/api/remap/1.2'
HEADERS = {
    'Authorization': f"Bearer {os.getenv('MOYSKLAD_TOKEN')}",
    'Accept-Encoding': 'gzip',
}


class MoyskladError(RuntimeError):
    """МойСклад недоступен или ответил ошибкой."""


def _get(path, params=None):
    try:
        data = ms_http.get(f'{BASE}{path}', headers=HEADERS, params=params).json()
    except Exception as exc:  # сеть, таймаут, некорректный JSON
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if isinstance(data, dict) and data.get('errors'):
        raise MoyskladError(f'МойСклад вернул ошибку: {data["errors"]}')
    return data


def _orders_by_text(text, *, limit=10):
    """Заказы покупателя, где встречается текст (ищем номер отправления)."""
    rows = _get('/entity/customerorder', {'search': text, 'limit': limit}).get('rows', [])
    return rows


def _order_by_external_code(external_code):
    """Наш заказ сайта: демон 06 кладёт номер заказа сайта в externalCode."""
    rows = _get(
        '/entity/customerorder', {'filter': f'externalCode={external_code}', 'limit': 1}
    ).get('rows', [])
    return rows[0] if rows else None


def _summary(order):
    if not order:
        return None
    return {
        'id': order.get('id'),
        'name': order.get('name'),
        'sum': (order.get('sum') or 0) / 100,
        'paid': (order.get('payedSum') or 0) / 100,
        'agent_href': ((order.get('agent') or {}).get('meta') or {}).get('href', ''),
        'description': (order.get('description') or '')[:200],
        'external_code': order.get('externalCode') or '',
    }


def find_duplicates(*, limit=50):
    """Пары «наш заказ сайта ↔ дубль от синхронизации» по отправлениям Ozon.

    Возвращает список словарей: отправление, наш заказ, найденный дубль и то,
    что из дубля стоит перенести к нам.
    """
    postings = (
        OzonPosting.objects
        .select_related('quote')
        .exclude(posting_number='')
        .order_by('-created_at')[:limit]
    )

    pairs = []
    for posting in postings:
        quote = posting.quote
        site_order = None
        if quote and quote.site_order_id:
            site_order = _order_by_external_code(quote.site_order_id)

        # Синхронизация пишет номер отправления в комментарий своего заказа
        candidates = [
            row for row in _orders_by_text(posting.posting_number)
            if not site_order or row.get('id') != site_order.get('id')
        ]

        pairs.append({
            'posting_number': posting.posting_number,
            'posting_status': posting.status,
            'site_order': _summary(site_order),
            'duplicates': [_summary(row) for row in candidates],
            'transferable': {
                'Номер отправления Ozon': posting.posting_number,
                'Статус отправления': posting.status,
                'Схема': posting.get_schema_display(),
            },
        })

    return pairs
