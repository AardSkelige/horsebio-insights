"""Поиск дублей в МойСклад по заказам Ozon Доставки.

На одну покупку получается два документа: наш — заведённый по письму сайта (там
покупатель, оплата и полная сумма) и чужой — созданный синхронизацией
МойСклад ↔ Ozon по отправлению (контрагент «Озон», сумма без доставки, без
оплаты). Второй мешает учёту, но полезное в нём есть: номер отправления, дата
отгрузки, статус от Ozon.

Порядок работы: сначала переносим полезное из дубля в наш заказ, только потом
удаляем дубль. Удаление идёт с четырьмя предохранителями — сведения должны
оказаться в нашем заказе, в комментарии документа должен стоять номер именно
нашего отправления, документ должен принадлежать каналу Ozon, и он не должен
совпадать с нашим заказом сайта. Не нашли наш заказ — дубль остаётся жить:
он единственный, где есть номер отправления, и удалять его некуда переносить
значит стереть эти сведения совсем.
"""

import logging
import os
import re
from pathlib import Path

from django.db.models import Q
from django.utils import timezone
from dotenv import load_dotenv

from msapi import http as ms_http
from ozon_logistics.models import OzonPosting

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

BASE = 'https://api.moysklad.ru/api/remap/1.2'

# Как часто перепроверять отправление, по которому уже всё разобрано. Дубль
# создаёт синхронизация МойСклад ↔ Ozon, и теоретически она может завести его
# заново — но не за пять минут, а раз в сутки перепроверить достаточно.
RECHECK_AFTER = timezone.timedelta(hours=24)


def _headers():
    """Собираем на каждый запрос: сменённый токен не должен требовать перезапуска."""
    return {
        'Authorization': f"Bearer {os.getenv('MOYSKLAD_TOKEN')}",
        'Accept-Encoding': 'gzip',
    }


class MoyskladError(RuntimeError):
    """МойСклад недоступен или ответил ошибкой."""


# Метка, по которой видно, что данные из дубля уже перенесены. Номер отправления
# входит в неё намеренно: Ozon дробит заказ на несколько отправлений, и общая
# метка без номера выдала бы второе отправление за уже перенесённое.
TRANSFER_MARKER = 'Ozon Доставка (из отправления):'


def _marker_for(posting_number):
    return f'{TRANSFER_MARKER} {posting_number}'


def _get(path, params=None):
    try:
        data = ms_http.get(f'{BASE}{path}', headers=_headers(), params=params).json()
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
        data = ms_http.put(f'{BASE}{path}', headers=_headers(), json=payload).json()
    except Exception as exc:
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if isinstance(data, dict) and data.get('errors'):
        raise MoyskladError(f'МойСклад отказал в изменении: {data["errors"]}')
    return data


def _delete(path):
    try:
        response = ms_http.delete(f'{BASE}{path}', headers=_headers())
    except Exception as exc:
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if response.status_code not in (200, 204):
        raise MoyskladError(
            f'МойСклад отказал в удалении ({response.status_code}): {response.text[:300]}'
        )
    return True


def _mentions_posting(text, posting_number):
    """Номер отправления упомянут целиком, а не как часть другого номера.

    Отправления заказа Ozon различаются суффиксом: «…-0375-1» — префикс
    «…-0375-11», и проверка простым вхождением подстроки приняла бы одно
    за другое, стерев не тот документ.
    """
    pattern = rf'(?<![\w-]){re.escape(posting_number)}(?![\w-])'
    return re.search(pattern, text or '') is not None


def _is_ozon_document(order):
    """Документ создан синхронизацией Ozon, а не нами.

    Смотрим и канал продаж, и контрагента: у заказа сайта канал «Сайт Horse-Bio»
    и контрагент — живой покупатель.
    """
    channel = ((order.get('salesChannel') or {}).get('name') or '').upper()
    agent = ((order.get('agent') or {}).get('name') or '').upper()
    return any('ОЗОН' in value or 'OZON' in value for value in (channel, agent))


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


def find_duplicates(*, limit=50, include_resolved=True):
    """Пары «наш заказ сайта ↔ дубль от синхронизации» по отправлениям Ozon.

    Возвращает список словарей: отправление, наш заказ, найденный дубль и то,
    что из дубля стоит перенести к нам.

    `include_resolved=False` пропускает отправления, разобранные меньше суток
    назад: на каждое уходит два запроса в МойСклад, а задача крутится каждые
    пять минут — перебирать по кругу давно разобранное незачем.
    """
    postings = (
        OzonPosting.objects
        .select_related('quote')
        .exclude(posting_number='')
    )
    if not include_resolved:
        postings = postings.filter(
            Q(duplicates_checked_at__isnull=True)
            | Q(duplicates_checked_at__lt=timezone.now() - RECHECK_AFTER)
        )
    postings = postings.order_by('-created_at')[:limit]

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


def _transfer_text(pair, duplicates, description=''):
    """Что дописать в наш заказ: сведения из дублей, которых у нас ещё нет.

    Берём именно те документы, что прошли предохранители: в `duplicates_raw`
    лежит вся выдача поиска, включая чужие документы, и их описания в нашем
    заказе оказаться не должны.

    Что уже перенесено, определяем по содержимому, а не по метке отправления:
    синхронизация может завести дубль заново, с новым комментарием, и метка
    «это отправление уже переносили» отправила бы его в удаление вместе с
    неперенесённым текстом. Пустая строка означает «дописывать нечего».
    """
    lines = [
        text for text in (
            (duplicate.get('description') or '').strip() for duplicate in duplicates
        )
        if text and text not in description
    ]
    if not lines and not any((d.get('description') or '').strip() for d in duplicates):
        # Комментария нет ни у одного дубля — переносим хотя бы то, что знаем сами
        fallback = f"Номер отправления: {pair['posting_number']}"
        if fallback not in description:
            lines = [fallback, f"Статус: {pair['posting_status'] or 'неизвестен'}"]
    if not lines:
        return ''
    return '\n'.join([_marker_for(pair['posting_number'])] + lines)


def _mark_checked(posting_number):
    """Отметить, что отправление просмотрено: в ближайшие сутки не возвращаемся."""
    OzonPosting.objects.filter(posting_number=posting_number).update(
        duplicates_checked_at=timezone.now()
    )


def resolve_duplicate(pair, *, apply=False):
    """Переносит сведения в заказ сайта и удаляет дубль.

    Без `apply` только сообщает, что было бы сделано. Удаляем документ лишь
    после того, как его сведения оказались в нашем заказе: пока переносить
    некуда, дубль — единственное место, где живут номер отправления и статус.
    """
    result = {
        'posting_number': pair['posting_number'],
        'transferred': False,
        'deleted': [],
        'skipped': [],
    }

    site_order = pair.get('site_order_raw')
    duplicates = pair.get('duplicates_raw') or []

    safe_to_delete = []
    for duplicate in duplicates:
        name = duplicate.get('name')
        if site_order and duplicate.get('id') == site_order.get('id'):
            result['skipped'].append((name, 'это наш заказ сайта'))
            continue
        if not _mentions_posting(duplicate.get('description'), pair['posting_number']):
            result['skipped'].append((name, 'в комментарии нет номера отправления'))
            continue
        if not _is_ozon_document(duplicate):
            result['skipped'].append((name, 'документ не из канала Ozon'))
            continue
        safe_to_delete.append(duplicate)

    if not safe_to_delete:
        # Причины пропуска постоянные — чужой документ чужим и останется,
        # так что возвращаться сюда через пять минут незачем.
        if apply:
            _mark_checked(pair['posting_number'])
        return result

    if not site_order:
        # Единственный документ с номером отправления — переносить некуда, а
        # удалить значит стереть сведения совсем. Оставляем и зовём человека.
        for duplicate in safe_to_delete:
            result['skipped'].append(
                (duplicate.get('name'), 'наш заказ сайта не найден — переносить некуда, дубль оставлен')
            )
        logger.warning(
            'Ozon Доставка: по отправлению %s есть дубль, но наш заказ сайта не найден — '
            'дубль оставлен, разберитесь вручную', pair['posting_number'],
        )
        # Отмечаем как просмотренное: разобрать это может только человек, а
        # предупреждение раз в сутки читается, в отличие от него же каждые
        # пять минут.
        if apply:
            _mark_checked(pair['posting_number'])
        return result

    # Сначала перенос: если удалить раньше, сведения об отправлении потеряются
    description = site_order.get('description') or ''
    addition = _transfer_text(pair, safe_to_delete, description)
    if addition:
        result['transfer_text'] = addition
        if apply:
            _put(f"/entity/customerorder/{site_order['id']}", {
                'description': f'{description}\n\n{addition}'.strip(),
            })
        result['transferred'] = True

    for duplicate in safe_to_delete:
        if apply:
            _delete(f"/entity/customerorder/{duplicate['id']}")
            logger.info(
                'Ozon Доставка: удалён дубль №%s (отправление %s)',
                duplicate.get('name'), pair['posting_number'],
            )
        result['deleted'].append(duplicate.get('name'))

    if apply:
        _mark_checked(pair['posting_number'])

    return result
