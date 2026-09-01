"""Расчёт доставки и создание заказа в Ozon.

Порядок жёстко задан документацией: расчёт (`checkout`) делается при оформлении,
а заказ создаётся ТОЛЬКО после подтверждения оплаты — и изменить его состав
после этого нельзя.
"""

import logging
from decimal import Decimal

from django.utils import timezone

from ozon_logistics.models import OzonDeliveryQuote
from ozon_logistics.services.client import (
    OzonLogisticsClient, OzonLogisticsError, OzonLogisticsTimeout, normalize_phone,
)

logger = logging.getLogger(__name__)

CURRENCY = 'RUB'
NANOS_IN_UNIT = Decimal('1000000000')


class OzonOrderError(RuntimeError):
    """Заказ создать не удалось."""


def _money(amount):
    """Рубли → формат Ozon: целые units и дробные nanos (миллиардные доли)."""
    value = Decimal(str(amount))
    units = int(value)
    nanos = int((value - units) * NANOS_IN_UNIT)
    return {'currency_code': CURRENCY, 'units': units, 'nanos': nanos}


def _total_commission(splits):
    """Суммарная стоимость логистики по всем отправлениям заказа."""
    total = Decimal('0')
    for split in splits:
        amount = ((split.get('commissions') or {}).get('total') or {}).get('amount')
        if amount is not None:
            total += Decimal(str(amount))
    return total


def create_quote(*, phone, items, map_point_id=None, coordinates=None,
                 courier_address=None, client=None):
    """Считает доставку и сохраняет вариант до момента оплаты.

    `items` — список {'sku': ..., 'quantity': ...}.
    """
    client = client or OzonLogisticsClient()
    response = client.checkout(
        phone=phone, items=items, map_point_id=map_point_id, coordinates=coordinates
    )

    quote = OzonDeliveryQuote.objects.create(
        phone=normalize_phone(phone),
        items=items,
        map_point_id=map_point_id,
        courier_address=courier_address,
        checkout_response=response,
        delivery_cost=_total_commission(response.get('splits') or []),
    )
    logger.info(
        'Ozon Доставка: расчёт %s — вариантов %s, доступен: %s',
        quote.id, len(quote.splits), quote.is_deliverable,
    )
    return quote


def build_order_payload(quote, *, buyer, recipient=None, prices):
    """Собирает запрос на создание заказа из сохранённого расчёта.

    `prices` — цены позиций в рублях по sku: их берём из оплаченного заказа
    сайта, а не из расчёта, потому что в checkout цены не участвуют, а в заказ
    должна попасть та сумма, которую покупатель заплатил (со скидками).
    """
    if not quote.is_deliverable:
        raise OzonOrderError(
            f'Доставка недоступна: {", ".join(quote.unavailable_reasons()) or "причина не указана"}'
        )

    splits = []
    for split in quote.splits:
        if not split.get('commissions'):
            continue  # вариант недоступен — в заказ не идёт

        method = split.get('delivery_method') or {}
        timeslots = method.get('timeslots') or []
        if not timeslots:
            raise OzonOrderError('В расчёте нет ни одного таймслота доставки')
        timeslot = timeslots[0]

        items = []
        for item in split.get('items') or []:
            sku = item.get('sku')
            if sku is None:
                raise OzonOrderError('В расчёте есть позиция без sku')
            price = prices.get(int(sku))
            if price is None:
                raise OzonOrderError(f'Не передана цена позиции sku {sku}')
            items.append({
                'sku': int(sku),
                'quantity': int(item.get('quantity') or 1),
                'price': _money(price),
            })

        splits.append({
            'delivery_method': {
                'delivery_method_id': method.get('id'),
                'delivery_type': method.get('delivery_type'),
                'timeslot_id': timeslot.get('timeslot_id'),
                'logistic_date_range': timeslot.get('logistic_date_range'),
            },
            'items': items,
            'warehouse_id': split.get('warehouse_id'),
        })

    if not splits:
        raise OzonOrderError('Нет доступных отправлений для заказа')

    if quote.map_point_id:
        delivery = {'pick_up': {'map_point_id': int(quote.map_point_id)}}
    elif quote.courier_address:
        delivery = {'courier': quote.courier_address}
    else:
        raise OzonOrderError('В расчёте нет ни пункта выдачи, ни адреса курьера')

    # Получатель может отличаться от покупателя; если не указан — дублируем покупателя,
    # как требует документация.
    recipient = recipient or {
        'recipient_first_name': buyer.get('first_name', ''),
        'recipient_last_name': buyer.get('last_name', ''),
        'recipient_middle_name': buyer.get('middle_name', ''),
        'recipient_phone': buyer.get('phone', ''),
    }

    return {
        'buyer': {**buyer, 'phone': normalize_phone(buyer.get('phone'))},
        'recipient': {
            **recipient,
            'recipient_phone': normalize_phone(recipient.get('recipient_phone')),
        },
        'delivery_schema': 'MIX',
        'delivery': delivery,
        'splits': splits,
    }


def create_order(quote, *, buyer, recipient=None, prices, client=None):
    """Создаёт заказ в Ozon по сохранённому расчёту.

    Повторный вызов для уже созданного заказа ничего не делает: состав менять
    нельзя, а дубль означал бы вторую отгрузку тому же покупателю.
    """
    if quote.status == OzonDeliveryQuote.STATUS_ORDERED:
        logger.info('Ozon Доставка: заказ по расчёту %s уже создан (%s)', quote.id, quote.order_number)
        return quote

    payload = build_order_payload(quote, buyer=buyer, recipient=recipient, prices=prices)

    client = client or OzonLogisticsClient()
    quote.attempts += 1
    try:
        response = client.order_create(payload)
    except OzonLogisticsTimeout as exc:
        # Ответ потерян, но заказ мог создаться. Повтор дал бы вторую посылку,
        # поэтому останавливаемся и зовём человека.
        quote.status = OzonDeliveryQuote.STATUS_UNKNOWN
        quote.error = f'Ozon не ответил вовремя, проверьте заказ в личном кабинете: {exc}'[:2000]
        quote.save(update_fields=['status', 'error', 'attempts'])
        logger.error(
            'Ozon Доставка: неизвестный исход по расчёту %s — проверьте в ЛК Ozon: %s',
            quote.id, exc,
        )
        raise OzonOrderError(quote.error) from exc
    except OzonLogisticsError as exc:
        quote.status = OzonDeliveryQuote.STATUS_FAILED
        quote.error = str(exc)[:2000]
        quote.save(update_fields=['status', 'error', 'attempts'])
        logger.error(
            'Ozon Доставка: заказ по расчёту %s не создан (попытка %s из %s): %s',
            quote.id, quote.attempts, OzonDeliveryQuote.MAX_ATTEMPTS, exc,
        )
        raise OzonOrderError(str(exc)) from exc

    order_number = response.get('order_number') or ''
    quote.status = OzonDeliveryQuote.STATUS_ORDERED
    quote.order_number = order_number
    quote.ordered_at = timezone.now()
    quote.error = ''
    quote.save(update_fields=['status', 'order_number', 'ordered_at', 'error', 'attempts'])

    logger.info('Ozon Доставка: создан заказ %s по расчёту %s', order_number, quote.id)
    return quote


def cancel_order(quote, *, reason_id=None, reason_message='', client=None):
    """Отменяет заказ Ozon, созданный по этому расчёту.

    Отмена асинхронная: успешный ответ означает, что запрос принят, а не что
    заказ уже отменён. Поэтому деньги покупателю возвращают только после того,
    как `cancel_status` подтвердит отмену — так требует документация.

    Причину можно не указывать: возьмём первую из допустимых для этого заказа.
    Список причин документация просит запрашивать только при реальной надобности,
    поэтому лезем за ним лишь когда `reason_id` не передан.
    """
    if quote.status != OzonDeliveryQuote.STATUS_ORDERED or not quote.order_number:
        raise OzonOrderError('По этому расчёту заказ в Ozon не создавался')

    client = client or OzonLogisticsClient()

    check = client.cancel_check(quote.order_number)
    if not check.get('cancellable'):
        raise OzonOrderError(
            f'Ozon не разрешает отменить заказ {quote.order_number} — '
            'возможно, он уже собран или выдан'
        )

    if reason_id is None:
        reasons = (client.cancel_reasons_for_order(quote.order_number) or {}).get('reasons') or []
        if not reasons:
            raise OzonOrderError('Ozon не вернул ни одной допустимой причины отмены')
        reason_id = reasons[0].get('id')

    response = client.cancel_order(
        quote.order_number, reason_id=reason_id, reason_message=reason_message
    )
    logger.info(
        'Ozon Доставка: запрошена отмена заказа %s (причина %s)',
        quote.order_number, reason_id,
    )
    return response


def cancellation_state(quote, *, client=None):
    """Чем закончилась отмена. Деньги возвращаем только после подтверждения."""
    if not quote.order_number:
        raise OzonOrderError('По этому расчёту заказ в Ozon не создавался')
    client = client or OzonLogisticsClient()
    return client.cancel_status(quote.order_number)
