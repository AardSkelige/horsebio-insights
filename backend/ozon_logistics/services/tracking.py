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
from ozon_logistics.services.client import OzonLogisticsClient, OzonLogisticsError

logger = logging.getLogger(__name__)

MAX_PAGES = 20
PAGE_SIZE = 100
# Сколько номеров кладём в один фильтр Ozon. Списки в фильтрах не резиновые, а
# заказов со временем становится больше, чем помещается в один запрос.
CHUNK_SIZE = 50
# Заказ, у которого за это время так и не появилось ни одного отправления,
# из наблюдения выходит: иначе он остаётся в фильтре навсегда и список растёт
# сам по себе. Такой случай виден в уведомлениях, им занимается человек.
TRACK_DAYS = 90
# Запас по краям окна дат для FBO: заказ мог быть создан минутой раньше, чем
# записан у нас, а доставка — закончиться позже, чем мы спросили.
WINDOW_MARGIN = timezone.timedelta(days=1)


def _chunks(values, size=CHUNK_SIZE):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _window(quotes):
    """Окно дат для списка FBO: без него метод отвечает «date since or date to
    must not be empty», сколько бы номеров отправлений мы ни передали.

    Начало считаем от самого старого заказа под наблюдением, а не от TRACK_DAYS:
    застрявшая посылка остаётся в наблюдении и на сотый день, и окно должно
    доставать до неё.
    """
    oldest = min(quote.created_at for quote in quotes)
    return (oldest - WINDOW_MARGIN).isoformat(), (timezone.now() + WINDOW_MARGIN).isoformat()


def _active_quotes():
    """Заказы, за которыми ещё есть смысл следить.

    Отслеживаем, пока хоть одно отправление не дошло до конечного статуса —
    либо пока отправлений вообще не видели, но заказ ещё свежий.
    """
    quotes = (
        OzonDeliveryQuote.objects
        .filter(status=OzonDeliveryQuote.STATUS_ORDERED)
        .exclude(order_number='')
        .prefetch_related('postings_tracked')
    )
    # По created_at, а не по ordered_at: он проставляется только тем, что прошло
    # через create_order, и у заведённых иначе пуст.
    cutoff = timezone.now() - timezone.timedelta(days=TRACK_DAYS)

    active = []
    for quote in quotes:
        tracked = list(quote.postings_tracked.all())
        if tracked:
            # Отправление видели: следим, пока хоть одно не в конечном статусе.
            # Срок здесь не при чём — застрявшая посылка может отмениться и на
            # сотый день, а деньги за неё всё те же наши.
            if any(not posting.is_final for posting in tracked):
                active.append(quote)
        elif quote.created_at >= cutoff:
            # Отправлений не видели вовсе: ждём, но не вечно — иначе такой
            # заказ остаётся в фильтре навсегда.
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

    defaults = {
        'schema': schema,
        'cancel_reason': cancel_reason,
        'details': entry,
    }
    # Пустое значение — не новость, а её отсутствие: записывать его поверх
    # известного нельзя. Так у отправления пропадала связь с расчётом, а вместе
    # с ней — и заказ сайта в уведомлениях.
    if order_number:
        defaults['order_number'] = order_number
        quote = quote_by_order.get(order_number)
        if quote is not None:
            defaults['quote'] = quote
    if status:
        defaults['status'] = status

    posting, _ = OzonPosting.objects.update_or_create(
        posting_number=posting_number, defaults=defaults,
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

        # Транзакция только вокруг записи: держать её открытой на время похода
        # в Ozon значит занимать соединение к базе на все двадцать страниц.
        with transaction.atomic():
            stored = [
                posting for posting in (
                    _store(entry, schema=schema, quote_by_order=quote_by_order)
                    for entry in entries
                )
                if posting is not None
            ]

        for posting in stored:
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
    stats = {'quotes': len(quotes), 'seen': 0, 'need_attention': 0, 'errors': []}
    if not quotes:
        return stats

    client = client or OzonLogisticsClient()
    quote_by_order = {q.order_number: q for q in quotes}
    order_numbers = list(quote_by_order)
    posting_numbers = [n for q in quotes for n in (q.postings or [])]
    since, to = _window(quotes)

    def gather(batches, fetch, schema):
        """Схемы независимы: отказ в правах на одну не должен гасить другую.

        До 17.09.2026 исключение из FBO обрывало весь прогон, и статусы не
        обновлялись вообще — включая FBS, который в тот момент работал.
        """
        for batch in batches:
            try:
                _collect(
                    lambda cursor, batch=batch: fetch(batch, cursor),
                    schema=schema, quote_by_order=quote_by_order, stats=stats,
                )
            except OzonLogisticsError as exc:
                stats['errors'].append(f'{schema}: {exc}')
                logger.error('Ozon Доставка: не удалось получить отправления %s: %s', schema, exc)

    # FBS ищется по номерам заказов — это и есть наш ключ
    gather(
        _chunks(order_numbers),
        lambda batch, cursor: client.posting_fbs_list(
            order_numbers=batch, limit=PAGE_SIZE, cursor=cursor
        ),
        OzonPosting.SCHEMA_FBS,
    )

    # FBO фильтруется только по номерам отправлений, поэтому нужны те, что
    # Ozon вернул при создании заказа
    gather(
        _chunks(posting_numbers),
        lambda batch, cursor: client.posting_fbo_list(
            posting_numbers=batch, since=since, to=to, limit=PAGE_SIZE, cursor=cursor
        ),
        OzonPosting.SCHEMA_FBO,
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
