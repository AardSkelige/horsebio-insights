"""Синхронизация сопоставления «наш артикул → sku в Ozon».

Ozon Доставка возит товары из каталога Ozon: в расчёт доставки и в заказ уходят
offer_id и sku. sku выдаёт сам Ozon, в МойСклад его нет, поэтому держим таблицу
у себя и обновляем периодически.
"""

import logging

from django.utils import timezone

from ozon_logistics.models import OzonProduct
from ozon_logistics.services.client import OzonLogisticsClient

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000  # /v3/product/list отдаёт до 1000 товаров за раз
MAX_PAGES = 100   # предохранитель от бесконечной пагинации


def sync_products(*, client=None):
    """Тянет весь каталог Ozon и обновляет таблицу сопоставления.

    Возвращает сводку: сколько получено, создано, обновлено, у скольких есть
    остатки FBS (то есть годны для Ozon Доставки).
    """
    client = client or OzonLogisticsClient()
    stats = {'fetched': 0, 'created': 0, 'updated': 0, 'skipped_without_sku': 0}
    last_id = None
    seen_offer_ids = []

    for _ in range(MAX_PAGES):
        response = client.product_list(limit=PAGE_SIZE, last_id=last_id)
        result = response.get('result') or {}
        items = result.get('items') or []
        if not items:
            break

        for item in items:
            stats['fetched'] += 1
            offer_id = (item.get('offer_id') or '').strip()
            sku = item.get('sku')
            # Товар без sku в Ozon Доставке бесполезен: заказ по нему не создать.
            if not offer_id or not sku:
                stats['skipped_without_sku'] += 1
                continue

            _, created = OzonProduct.objects.update_or_create(
                offer_id=offer_id,
                defaults={
                    'sku': sku,
                    'product_id': item.get('product_id'),
                    'has_fbs_stocks': bool(item.get('has_fbs_stocks')),
                    'has_fbo_stocks': bool(item.get('has_fbo_stocks')),
                    'archived': bool(item.get('archived')),
                },
            )
            stats['created' if created else 'updated'] += 1
            seen_offer_ids.append(offer_id)

        last_id = result.get('last_id')
        if not last_id or len(items) < PAGE_SIZE:
            break
    else:
        logger.warning('Ozon Доставка: пагинация каталога прервана на %s страницах', MAX_PAGES)

    stats['sellable'] = OzonProduct.objects.filter(
        has_fbs_stocks=True, archived=False
    ).count()
    stats['total_stored'] = OzonProduct.objects.count()
    stats['synced_at'] = timezone.now().isoformat()

    logger.info(
        'Ozon Доставка: каталог синхронизирован — получено %(fetched)s, '
        'создано %(created)s, обновлено %(updated)s, годно для доставки %(sellable)s',
        stats,
    )
    return stats
