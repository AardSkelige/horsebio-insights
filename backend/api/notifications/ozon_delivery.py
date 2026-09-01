"""Уведомления по доставке Ozon в разделе «Заказы сайта».

Четыре повода, и все про одно: деньги покупателя у нас, а товар до него не
дошёл или не дойдёт. Ozon разрешает создавать заказ только после оплаты, поэтому к
моменту любой из этих ситуаций оплата уже прошла.

1. **Отправление отменено или не выкуплено** — Ozon отменил сам, покупатель не
   забрал из пункта или отказался при получении. Деньги надо вернуть.
2. **Заказ в Ozon не создался** — покупатель оплатил доставку Ozon, но
   отправление не завели: закончился товар, устарел расчёт. Клиент ждёт посылку,
   которой нет.
3. **Исход создания неизвестен** — Ozon не ответил вовремя. Заказ мог создаться,
   а мог и нет; повторять вслепую нельзя, иначе покупатель получит две посылки.
4. **Возврат** — посылка физически едет обратно на склад: её надо принять, а
   покупателю вернуть деньги. Это отдельный повод от отмены: отмена говорит про
   статус доставки, возврат — про товар, который сейчас в пути к нам.

Отпечаток строится из статуса и номера: пока состояние то же, уведомление
остаётся прочитанным. Появился новый статус — человек увидит его снова.
"""

from ozon_logistics.models import OzonDeliveryQuote, OzonPosting, OzonReturn

from .core import CRITICAL, WARNING, Notification, provider

RETURN_ACTION = 'Верните оплату кнопкой «Полный возврат» в админке сайта'


def _order_label(quote):
    """Чем назвать заказ, чтобы человек его узнал."""
    if quote and quote.site_order_id:
        return f'заказ сайта №{quote.site_order_id}'
    return 'заказ сайта не найден'


@provider('site-orders')
def ozon_delivery_notifications():
    yield from _undelivered()
    yield from _failed_orders()
    yield from _uncertain_orders()
    yield from _returns()


def _undelivered():
    """Товар не доехал: отмена, невыкуп, непринятая посылка."""
    postings = (
        OzonPosting.objects
        .select_related('quote')
        .filter(status__in=OzonPosting.ALARMING_STATUSES, handled_at__isnull=True)
    )

    for posting in postings:
        reason = posting.cancel_reason or 'причину Ozon не назвал'
        yield Notification(
            key=f'ozon-delivery:undelivered:{posting.posting_number}',
            level=WARNING,
            title=f'Доставка Ozon не состоялась — {_order_label(posting.quote)}',
            body=(
                f'Отправление {posting.posting_number} в статусе «{posting.status}». '
                f'{reason}. Оплата покупателя у нас.'
            ),
            action=RETURN_ACTION,
            fingerprint=f'{posting.posting_number}:{posting.status}',
        )


def _failed_orders():
    """Оплата прошла, а отправление создать не удалось."""
    quotes = OzonDeliveryQuote.objects.filter(
        status=OzonDeliveryQuote.STATUS_FAILED,
        attempts__gte=OzonDeliveryQuote.MAX_ATTEMPTS,
    ).exclude(site_order_id='')

    for quote in quotes:
        yield Notification(
            key=f'ozon-delivery:failed:{quote.id}',
            level=CRITICAL,
            title=f'Доставка Ozon не создана — {_order_label(quote)}',
            body=(
                f'Попыток: {quote.attempts}. Ozon отказал: '
                f'{(quote.error or "без объяснения")[:200]}. '
                'Покупатель оплатил, но отправления нет.'
            ),
            action='Оформите доставку другой службой или верните оплату',
            fingerprint=f'{quote.id}:{quote.attempts}',
        )


def _uncertain_orders():
    """Ozon не ответил: заказ мог создаться, а мог и нет."""
    quotes = OzonDeliveryQuote.objects.filter(
        status=OzonDeliveryQuote.STATUS_UNKNOWN
    ).exclude(site_order_id='')

    for quote in quotes:
        yield Notification(
            key=f'ozon-delivery:uncertain:{quote.id}',
            level=CRITICAL,
            title=f'Неизвестно, создана ли доставка Ozon — {_order_label(quote)}',
            body=(
                'Ozon не ответил вовремя. Отправление могло создаться, поэтому '
                'повторять нельзя — покупатель получит две посылки.'
            ),
            action='Найдите заказ в личном кабинете Ozon и решите: оставить или отменить',
            fingerprint=f'{quote.id}:unknown',
        )


def _returns():
    """Товар едет обратно: принять на складе и вернуть оплату."""
    for item in OzonReturn.objects.select_related('quote').filter(handled_at__isnull=True):
        kind = 'Полный возврат' if item.is_full else 'Частичный возврат'
        yield Notification(
            key=f'ozon-delivery:return:{item.return_id}',
            level=WARNING,
            title=f'{kind} Ozon — {_order_label(item.quote)}',
            body=(
                f'Отправление {item.posting_number}. '
                f'{item.reason or "Причину Ozon не назвал"}. '
                f'Статус: {item.status_name or "неизвестен"}.'
            ),
            action='Примите товар на складе и верните оплату покупателю',
            fingerprint=f'{item.return_id}:{item.status_sys_name}',
        )
