"""Возвраты по отправлениям Ozon Доставки.

Отправление может доехать и всё равно вернуться: покупатель отказался при
вручении или не забрал посылку из пункта. Тогда товар физически едет обратно на
склад, и его надо принять, а покупателю вернуть деньги. Отслеживаем возвраты
только по своим отправлениям — возвраты маркетплейса живут отдельно, ими
занимаются скрипты в `moysklad/horsebio/01_daemons/03_returns`.
"""

import logging

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ozon_logistics.models import OzonPosting, OzonReturn
from ozon_logistics.services.client import OzonLogisticsClient

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 20
# Возврат ищем только по свежим отправлениям: по доставленным год назад Ozon
# ничего не вернёт, а запрос стоит времени.
TRACK_DAYS = 90


def _tracked_postings():
    """Отправления, по которым имеет смысл спрашивать возвраты."""
    since = timezone.now() - timezone.timedelta(days=TRACK_DAYS)
    return list(
        OzonPosting.objects
        .select_related('quote')
        .filter(created_at__gte=since)
        .exclude(posting_number='')
    )


def _store(entry, *, quote_by_posting):
    return_id = str(entry.get('id') or '')
    posting_number = entry.get('posting_number') or ''
    if not return_id or not posting_number:
        return None

    visual_status = ((entry.get('visual') or {}).get('status') or {})
    logistic = entry.get('logistic') or {}
    return_date = logistic.get('return_date')

    stored, _ = OzonReturn.objects.update_or_create(
        return_id=return_id,
        defaults={
            'posting_number': posting_number,
            'order_number': entry.get('order_number') or '',
            'quote': quote_by_posting.get(posting_number),
            'return_type': entry.get('type') or '',
            'schema': entry.get('schema') or '',
            'reason': (entry.get('return_reason_name') or '')[:500],
            'status_name': (visual_status.get('display_name') or '')[:200],
            'status_sys_name': (visual_status.get('sys_name') or '')[:100],
            'return_date': parse_datetime(return_date) if return_date else None,
            'details': entry,
        },
    )
    return stored


def sync_returns(*, client=None):
    """Забирает возвраты по нашим отправлениям и сохраняет их."""
    postings = _tracked_postings()
    stats = {'postings': len(postings), 'seen': 0, 'need_attention': 0}
    if not postings:
        return stats

    client = client or OzonLogisticsClient()
    quote_by_posting = {p.posting_number: p.quote for p in postings}
    posting_numbers = list(quote_by_posting)

    last_id = None
    for _ in range(MAX_PAGES):
        response = client.returns_list(
            posting_numbers=posting_numbers, limit=PAGE_SIZE, last_id=last_id
        )
        entries = response.get('returns') or []
        if not entries:
            break

        for entry in entries:
            stored = _store(entry, quote_by_posting=quote_by_posting)
            if stored is None:
                continue
            stats['seen'] += 1
            if stored.needs_attention:
                stats['need_attention'] += 1
                logger.warning(
                    'Ozon Доставка: возврат %s по отправлению %s (%s) — принять товар '
                    'и вернуть деньги',
                    stored.return_id, stored.posting_number,
                    stored.reason or 'причина не указана',
                )

        if not response.get('has_next'):
            break
        last_id = entries[-1].get('id')

    logger.info(
        'Ozon Доставка: возвраты обновлены — отправлений %(postings)s, возвратов '
        '%(seen)s, требуют внимания %(need_attention)s', stats,
    )
    return stats


def returns_needing_attention():
    """Возвраты, которые ещё никто не разобрал."""
    return OzonReturn.objects.filter(handled_at__isnull=True)


def mark_handled(return_id):
    """Отметить, что возврат разобран: товар принят, деньги возвращены."""
    return OzonReturn.objects.filter(return_id=return_id).update(handled_at=timezone.now())
