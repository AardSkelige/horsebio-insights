"""Создание заказов Ozon по оплаченным заказам сайта.

Ozon разрешает создать заказ только после оплаты, а признак оплаты приходит
письмом Megagroup: демон 06 разбирает его в state-файл. Отсюда мы этот файл
только читаем — заведение заказов в МойСклад живёт отдельно и его логику мы
не трогаем.
"""

import json
import logging
import sys
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

from ozon_logistics.models import OzonDeliveryQuote, OzonProduct
from ozon_logistics.services import orders
from ozon_logistics.services.client import OzonLogisticsError
from ozon_logistics.services.oauth import OzonOAuthError

logger = logging.getLogger(__name__)

# Скидку по позициям раскладывает та же функция, что и для МойСклад: правило
# «позиции по РРЦ, скидка только в total» одно на оба потока, и расходиться им нельзя.
sys.path.insert(0, str(Path(settings.BASE_DIR) / 'moysklad' / 'horsebio' / '_shared'))
from order_email_utils import split_site_discount  # noqa: E402

QUOTE_FIELD = 'ozon_quote_id'
STATE_FILE = (
    Path(settings.BASE_DIR)
    / 'moysklad' / 'horsebio' / '01_daemons' / '06_order_email_sync'
    / 'data' / '.order_email_state.json'
)


def _read_state(path=None):
    """Читает state демона 06. Отсутствие файла — не ошибка: писем ещё не было."""
    path = Path(path or STATE_FILE)
    if not path.exists():
        logger.info('Ozon Доставка: state-файл заказов сайта не найден (%s)', path)
        return {}
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (ValueError, OSError) as exc:
        logger.error('Ozon Доставка: не читается state заказов сайта: %s', exc)
        return {}


def _money(raw):
    try:
        return Decimal(str(raw).replace(',', '.').strip())
    except (InvalidOperation, AttributeError):
        return None


def _prices_by_sku(latest):
    """Цены позиций в рублях по sku — те, что покупатель реально заплатил.

    В письме позиции идут по РРЦ, а скидка (промокод, акция) сидит только в
    `total`. Если взять `price` как есть, в Ozon уедет сумма больше оплаченной,
    поэтому раскладываем скидку тем же алгоритмом, что и для МойСклад.
    """
    items = latest.get('items') or []
    goods, articles = [], []
    for item in items:
        article = str(item.get('article') or '').strip()
        price = _money(item.get('price'))
        quantity = _money(item.get('quantity'))
        if not article or price is None or quantity is None or quantity <= 0:
            continue
        articles.append(article)
        goods.append({
            'article': article,
            'quantity': float(quantity),
            'price': int(price * 100),
        })

    if not goods:
        return {}

    total = _money(latest.get('total'))
    if total is not None:
        delivery_kopecks = int((_money(latest.get('delivery_cost')) or Decimal('0')) * 100)
        delivery = {'price': delivery_kopecks, 'quantity': 1} if delivery_kopecks else None
        _, residual = split_site_discount(goods, delivery, int(total * 100))
        if residual:
            # Скидка не легла ровно — цены могли не сойтись с оплатой до копеек
            logger.warning(
                'Ozon Доставка: скидка заказа сайта разложилась с остатком %s коп.', residual
            )

    sku_by_article = {
        product.offer_id: product.sku
        for product in OzonProduct.objects.filter(offer_id__in=set(articles))
    }

    # split_site_discount может расщепить позицию ради копеек, поэтому цену за
    # единицу считаем по суммарной стоимости артикула, а не по одной строке.
    totals = {}
    for line in goods:
        sku = sku_by_article.get(line['article'])
        if sku is None:
            continue
        amount, quantity = totals.get(int(sku), (0, 0.0))
        totals[int(sku)] = (
            amount + round(line['price'] * line['quantity']),
            quantity + line['quantity'],
        )

    return {
        sku: (Decimal(amount) / Decimal(str(quantity)) / 100).quantize(Decimal('0.01'))
        for sku, (amount, quantity) in totals.items()
        if quantity
    }


def _buyer(latest):
    fields = latest.get('field') or {}
    return {
        'first_name': fields.get('fio', ''),
        'last_name': fields.get('familia', ''),
        'middle_name': fields.get('otcestvo', ''),
        'phone': fields.get('phone', ''),
    }


def process_paid_orders(*, state_path=None, client=None):
    """Создаёт в Ozon заказы по оплаченным заказам сайта с сохранённым расчётом."""
    state = _read_state(state_path)
    stats = {'checked': 0, 'created': 0, 'skipped': 0, 'failed': 0}

    for order_id, entry in (state.get('orders') or {}).items():
        latest = (entry or {}).get('latest') or {}
        quote_id = str((latest.get('field') or {}).get(QUOTE_FIELD) or '').strip()
        if not quote_id:
            continue

        stats['checked'] += 1

        if not latest.get('paid'):
            # Заказ ещё не оплачен: Ozon запрещает создавать заказ до оплаты
            stats['skipped'] += 1
            continue

        # Значение приходит из формы сайта: там может оказаться что угодно, а
        # UUIDField на мусоре бросает ValidationError и обрывает весь прогон —
        # тогда ни один следующий оплаченный заказ не уедет в Ozon.
        try:
            uuid.UUID(quote_id)
            quote = OzonDeliveryQuote.objects.filter(pk=quote_id).first()
        except (ValueError, ValidationError):
            logger.warning(
                'Ozon Доставка: заказ сайта %s содержит нечитаемый ozon_quote_id %r',
                order_id, quote_id[:64],
            )
            stats['skipped'] += 1
            continue

        if quote is None:
            logger.warning(
                'Ozon Доставка: заказ сайта %s ссылается на неизвестный расчёт %s',
                order_id, quote_id,
            )
            stats['skipped'] += 1
            continue

        if not quote.needs_order:
            # Заказ создан, исход неизвестен или попытки исчерпаны — молча не
            # пропускаем только последнее, о нём должно быть видно в логе.
            if quote.attempts >= OzonDeliveryQuote.MAX_ATTEMPTS \
                    and quote.status == OzonDeliveryQuote.STATUS_FAILED:
                logger.error(
                    'Ozon Доставка: по заказу сайта %s исчерпаны попытки (%s), '
                    'доставка не создана: %s',
                    order_id, quote.attempts, quote.error[:200],
                )
            stats['skipped'] += 1
            continue

        if not quote.site_order_id:
            quote.site_order_id = str(order_id)
            quote.save(update_fields=['site_order_id'])
        elif quote.site_order_id != str(order_id):
            logger.warning(
                'Ozon Доставка: расчёт %s уже привязан к заказу сайта %s, '
                'а встретился в заказе %s — доставка второго заказа не создана',
                quote.id, quote.site_order_id, order_id,
            )
            stats['skipped'] += 1
            continue

        prices = _prices_by_sku(latest)
        if not prices:
            logger.error(
                'Ozon Доставка: у заказа сайта %s не удалось сопоставить цены позиций',
                order_id,
            )
            stats['failed'] += 1
            continue

        try:
            orders.create_order(quote, buyer=_buyer(latest), prices=prices, client=client)
        except (orders.OzonOrderError, OzonOAuthError, OzonLogisticsError) as exc:
            logger.error(
                'Ozon Доставка: заказ сайта %s не создан в Ozon: %s', order_id, exc
            )
            stats['failed'] += 1
            continue

        stats['created'] += 1
        logger.info(
            'Ozon Доставка: по заказу сайта %s создан заказ %s',
            order_id, quote.order_number,
        )

    return stats
