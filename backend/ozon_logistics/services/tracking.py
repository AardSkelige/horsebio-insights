"""Отслеживание отправлений Ozon по созданным нами заказам.

Покупатель не может отменить заказ в приложении Ozon, но заказ всё равно может
не доехать: Ozon отменит сам, покупатель не заберёт из пункта или откажется при
получении. Деньги при этом у нас — значит кто-то должен их вернуть, и для этого
надо вовремя увидеть статус.
"""

import logging

from django.db import transaction
from django.utils import timezone

from ozon_logistics.models import OzonDeliveryQuote, OzonPosting
from ozon_logistics.services.client import OzonLogisticsClient

logger = logging.getLogger(__name__)

MAX_PAGES = 20
PAGE_SIZE = 100


def _active_quotes():
    """Заказы, за которыми ещё есть смысл следить.

    Отслеживаем, пока хоть одно отправление не дошло до конечного статуса —
    либо пока отправлений вообще не видели.
    """
    quotes = OzonDeliveryQuote.objects.filter(
        status=OzonDeliveryQuote.STATUS_ORDERED
    ).exclude(order_number='')

    active = []
    for quote in quotes:
        tracked = list(quote.postings_tracked.all())
        if not tracked or any(not p.is_final for p in tracked):
            active.append(quote)
    return active


def _store(entry, *, schema, quote_by_order):
    posting_number = entry.get('posting_number')
    if not posting_number:
        return None

    order_number = entry.get('order_number') or ''
    status = entry.get('status') or ''
    cancellation = entry.get('cancellation') or {}
    cancel_reason = (cancellation.get('cancel_reason') or '')[:500]

    posting, _ = OzonPosting.objects.update_or_create(
        posting_number=posting_number,
        defaults={
            'order_number': order_number,
            'quote': quote_by_order.get(order_number),
            'schema': schema,
            'status': status,
            'cancel_reason': cancel_reason,
            'details': entry,
        },
    )
    return posting


def _collect(fetch, *, schema, quote_by_order, stats):
    """Проходит постранично и сохраняет отправления."""
    cursor = None
    for _ in range(MAX_PAGES):
        response = fetch(cursor)
        # У разных методов ответ лежит то в result, то в корне
        result = response.get('result')
        if isinstance(result, dict):
            entries = result.get('postings') or []
            cursor = result.get('cursor')
            has_next = result.get('has_next')
        else:
            entries = response.get('postings') or result or []
            cursor = response.get('cursor')
            has_next = response.get('has_next')

        for entry in entries:
            posting = _store(entry, schema=schema, quote_by_order=quote_by_order)
            if posting is None:
                continue
            stats['seen'] += 1
            if posting.needs_attention:
                stats['need_attention'] += 1
                logger.warning(
                    'Ozon Доставка: отправление %s в статусе %s — деньги покупателю '
                    'нужно вернуть вручную (%s)',
                    posting.posting_number, posting.status, posting.cancel_reason or 'без причины',
                )

        if not has_next or not cursor or not entries:
            break


def sync_postings(*, client=None):
    """Обновляет статусы отправлений по нашим заказам Ozon."""
    quotes = _active_quotes()
    stats = {'quotes': len(quotes), 'seen': 0, 'need_attention': 0}
    if not quotes:
        return stats

    client = client or OzonLogisticsClient()
    quote_by_order = {q.order_number: q for q in quotes}
    order_numbers = list(quote_by_order)
    posting_numbers = [n for q in quotes for n in (q.postings or [])]

    with transaction.atomic():
        # FBS ищется по номерам заказов — это и есть наш ключ
        _collect(
            lambda cursor: client.posting_fbs_list(
                order_numbers=order_numbers, limit=PAGE_SIZE, cursor=cursor
            ),
            schema=OzonPosting.SCHEMA_FBS, quote_by_order=quote_by_order, stats=stats,
        )

        # FBO фильтруется только по номерам отправлений, поэтому нужны те, что
        # Ozon вернул при создании заказа
        if posting_numbers:
            _collect(
                lambda cursor: client.posting_fbo_list(
                    posting_numbers=posting_numbers, limit=PAGE_SIZE, cursor=cursor
                ),
                schema=OzonPosting.SCHEMA_FBO, quote_by_order=quote_by_order, stats=stats,
            )

    logger.info(
        'Ozon Доставка: статусы обновлены — заказов %(quotes)s, отправлений %(seen)s, '
        'требуют внимания %(need_attention)s', stats,
    )
    return stats


def postings_needing_attention():
    """Отправления, из-за которых покупателю нужно вернуть деньги."""
    return OzonPosting.objects.filter(
        status__in=OzonPosting.ALARMING_STATUSES, handled_at__isnull=True
    )


def mark_handled(posting_number):
    """Отметить, что с отправлением разобрались (деньги вернули)."""
    return OzonPosting.objects.filter(posting_number=posting_number).update(
        handled_at=timezone.now()
    )
