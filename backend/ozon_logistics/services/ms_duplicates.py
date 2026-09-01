"""Поиск дублей в МойСклад по заказам Ozon Доставки.

На одну покупку получается два документа: наш — заведённый по письму сайта (там
покупатель, оплата и полная сумма) и чужой — созданный синхронизацией
МойСклад ↔ Ozon по отправлению (контрагент «Озон», сумма без доставки, без
оплаты). Второй мешает учёту, но полезное в нём есть: номер отправления, дата
отгрузки, статус от Ozon.

Порядок работы: сначала переносим полезное из дубля в наш заказ, только потом
удаляем дубль. Удаление идёт с тремя предохранителями — в комментарии документа
должен стоять номер именно нашего отправления, документ должен принадлежать
каналу Ozon, и он не должен совпадать с нашим заказом сайта.
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


# Метка, по которой видно, что данные из дубля уже перенесены
TRANSFER_MARKER = 'Ozon Доставка (из отправления):'


def _get(path, params=None):
    try:
        data = ms_http.get(f'{BASE}{path}', headers=HEADERS, params=params).json()
    except Exception as exc:  # сеть, таймаут, некорректный JSON
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if isinstance(data, dict) and data.get('errors'):
        raise MoyskladError(f'МойСклад вернул ошибку: {data["errors"]}')
    return data


def _orders_by_text(text, *, limit=10):
    """Заказы покупателя, где встречается текст (ищем номер отправления).

    Раскрываем канал продаж и контрагента: по ним отличаем документ
    синхронизации Ozon от нашего заказа сайта.
    """
    return _get('/entity/customerorder', {
        'search': text, 'limit': limit, 'expand': 'salesChannel,agent',
    }).get('rows', [])


def _put(path, payload):
    try:
        data = ms_http.put(f'{BASE}{path}', headers=HEADERS, json=payload).json()
    except Exception as exc:
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if isinstance(data, dict) and data.get('errors'):
        raise MoyskladError(f'МойСклад отказал в изменении: {data["errors"]}')
    return data


def _delete(path):
    try:
        response = ms_http.delete(f'{BASE}{path}', headers=HEADERS)
    except Exception as exc:
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if response.status_code not in (200, 204):
        raise MoyskladError(
            f'МойСклад отказал в удалении ({response.status_code}): {response.text[:300]}'
        )
    return True


def _is_ozon_document(order):
    """Документ создан синхронизацией Ozon, а не нами.

    Смотрим и канал продаж, и контрагента: у заказа сайта канал «Сайт Horse-Bio»
    и контрагент — живой покупатель.
    """
    channel = ((order.get('salesChannel') or {}).get('name') or '').upper()
    agent = ((order.get('agent') or {}).get('name') or '').upper()
    return 'ОЗОН' in channel or 'OZON' in channel or agent in ('ОЗОН', 'OZON')


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
            'site_order_raw': site_order,
            'duplicates': [_summary(row) for row in candidates],
            'duplicates_raw': candidates,
            'transferable': {
                'Номер отправления Ozon': posting.posting_number,
                'Статус отправления': posting.status,
                'Схема': posting.get_schema_display(),
            },
        })

    return pairs


def _transfer_text(pair):
    """Что дописать в наш заказ: сведения об отправлении из дубля."""
    lines = [TRANSFER_MARKER]
    for duplicate in pair['duplicates_raw']:
        description = (duplicate.get('description') or '').strip()
        if description:
            lines.append(description)
    if len(lines) == 1:
        # Комментария у дубля нет — переносим хотя бы то, что знаем сами
        lines.append(f"Номер отправления: {pair['posting_number']}")
        lines.append(f"Статус: {pair['posting_status'] or 'неизвестен'}")
    return '\n'.join(lines)


def resolve_duplicate(pair, *, apply=False):
    """Переносит сведения в заказ сайта и удаляет дубль.

    Без `apply` только сообщает, что было бы сделано. Удаляем лишь документы,
    прошедшие все проверки: номер нашего отправления в комментарии, канал Ozon,
    не наш заказ сайта.
    """
    result = {
        'posting_number': pair['posting_number'],
        'transferred': False,
        'deleted': [],
        'skipped': [],
    }

    site_order = pair.get('site_order_raw')
    duplicates = pair.get('duplicates_raw') or []
    if not duplicates:
        return result

    safe_to_delete = []
    for duplicate in duplicates:
        name = duplicate.get('name')
        if site_order and duplicate.get('id') == site_order.get('id'):
            result['skipped'].append((name, 'это наш заказ сайта'))
            continue
        if pair['posting_number'] not in (duplicate.get('description') or ''):
            result['skipped'].append((name, 'в комментарии нет номера отправления'))
            continue
        if not _is_ozon_document(duplicate):
            result['skipped'].append((name, 'документ не из канала Ozon'))
            continue
        safe_to_delete.append(duplicate)

    if not safe_to_delete:
        return result

    # Сначала перенос: если удалить раньше, сведения об отправлении потеряются
    if site_order:
        description = site_order.get('description') or ''
        if TRANSFER_MARKER not in description:
            addition = _transfer_text(pair)
            result['transfer_text'] = addition
            if apply:
                _put(f"/entity/customerorder/{site_order['id']}", {
                    'description': f'{description}\n\n{addition}'.strip(),
                })
            result['transferred'] = True
    else:
        result['skipped'].append((None, 'наш заказ сайта не найден — перенос невозможен'))

    for duplicate in safe_to_delete:
        if apply:
            _delete(f"/entity/customerorder/{duplicate['id']}")
            logger.info(
                'Ozon Доставка: удалён дубль №%s (отправление %s)',
                duplicate.get('name'), pair['posting_number'],
            )
        result['deleted'].append(duplicate.get('name'))

    return result
