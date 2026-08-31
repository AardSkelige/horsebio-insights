"""Создание заказов Ozon по оплаченным заказам сайта.

Ozon разрешает создать заказ только после оплаты, а признак оплаты приходит
письмом Megagroup: демон 06 разбирает его в state-файл. Отсюда мы этот файл
только читаем — заведение заказов в МойСклад живёт отдельно и его логику мы
не трогаем.
"""

import json
import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings

from ozon_logistics.models import OzonDeliveryQuote, OzonProduct
from ozon_logistics.services import orders
from ozon_logistics.services.client import OzonLogisticsError
from ozon_logistics.services.oauth import OzonOAuthError

logger = logging.getLogger(__name__)

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


def _prices_by_sku(items):
    """Цены позиций письма (артикул) переводим в цены по sku.

    В заказ Ozon должна попасть та цена, которую покупатель заплатил, — из
    письма, а не из расчёта: в checkout цен нет, а скидки сайт раскладывает
    именно по позициям.
    """
    articles = {str(item.get('article') or '').strip() for item in items}
    articles.discard('')
    sku_by_article = {
        product.offer_id: product.sku
        for product in OzonProduct.objects.filter(offer_id__in=articles)
    }

    prices = {}
    for item in items:
        article = str(item.get('article') or '').strip()
        sku = sku_by_article.get(article)
        price = _money(item.get('price'))
        if sku is None or price is None:
            continue
        prices[int(sku)] = price
    return prices


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
        quote_id = (latest.get('field') or {}).get(QUOTE_FIELD, '').strip()
        if not quote_id:
            continue

        stats['checked'] += 1

        if not latest.get('paid'):
            # Заказ ещё не оплачен: Ozon запрещает создавать заказ до оплаты
            stats['skipped'] += 1
            continue

        quote = OzonDeliveryQuote.objects.filter(pk=quote_id).first()
        if quote is None:
            logger.warning(
                'Ozon Доставка: заказ сайта %s ссылается на неизвестный расчёт %s',
                order_id, quote_id,
            )
            stats['skipped'] += 1
            continue

        if quote.status == OzonDeliveryQuote.STATUS_ORDERED:
            stats['skipped'] += 1
            continue

        if not quote.site_order_id:
            quote.site_order_id = str(order_id)
            quote.save(update_fields=['site_order_id'])

        prices = _prices_by_sku(latest.get('items') or [])
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
