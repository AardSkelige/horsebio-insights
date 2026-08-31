"""Локальная копия пунктов выдачи Ozon.

Точек около 94 тысяч, и метод отдаёт их одним куском. Обновляем раз в сутки
пачками, чтобы не держать всё в памяти процесса и не насиловать базу
поштучными запросами.
"""

import logging

from django.db import transaction
from django.utils import timezone

from ozon_logistics.models import OzonPickupPoint
from ozon_logistics.services.client import OzonLogisticsClient

logger = logging.getLogger(__name__)

BATCH_SIZE = 2000       # строк за один bulk-запрос к базе
DETAILS_CHUNK = 100     # предел /v1/delivery/point/info


def sync_pickup_points(*, client=None):
    """Обновляет координаты всех ПВЗ. Возвращает сводку."""
    client = client or OzonLogisticsClient()
    response = client.point_list()
    points = response.get('points') or []

    stats = {'fetched': len(points), 'created': 0, 'updated': 0, 'skipped': 0}
    if not points:
        logger.warning('Ozon Доставка: список ПВЗ пуст, таблицу не трогаем')
        stats['total_stored'] = OzonPickupPoint.objects.count()
        return stats

    known_ids = set(OzonPickupPoint.objects.values_list('map_point_id', flat=True))
    now = timezone.now()
    to_create, to_update = [], []

    for point in points:
        point_id = point.get('map_point_id')
        coordinate = point.get('coordinate') or {}
        latitude, longitude = coordinate.get('lat'), coordinate.get('long')
        if not point_id or latitude is None or longitude is None:
            stats['skipped'] += 1
            continue

        row = OzonPickupPoint(
            map_point_id=point_id, latitude=latitude, longitude=longitude, synced_at=now
        )
        (to_update if point_id in known_ids else to_create).append(row)

    with transaction.atomic():
        OzonPickupPoint.objects.bulk_create(to_create, batch_size=BATCH_SIZE)
        OzonPickupPoint.objects.bulk_update(
            to_update, ['latitude', 'longitude', 'synced_at'], batch_size=BATCH_SIZE
        )

    stats['created'] = len(to_create)
    stats['updated'] = len(to_update)
    stats['total_stored'] = OzonPickupPoint.objects.count()

    logger.info(
        'Ozon Доставка: ПВЗ обновлены — получено %(fetched)s, создано %(created)s, '
        'обновлено %(updated)s',
        stats,
    )
    return stats


def fetch_details(map_point_ids, *, client=None):
    """Подтягивает подробности точек и сохраняет их. Возвращает эти точки.

    Вызывается лениво — когда покупатель раскрыл пункт на карте. Уже известные
    подробности повторно не запрашиваем.
    """
    ids = [int(i) for i in map_point_ids][:DETAILS_CHUNK]
    if not ids:
        return []

    stored = {p.map_point_id: p for p in OzonPickupPoint.objects.filter(map_point_id__in=ids)}
    missing = [i for i in ids if i not in stored or stored[i].details is None]

    if missing:
        client = client or OzonLogisticsClient()
        response = client.point_info(missing)
        now = timezone.now()
        updated = []

        for entry in response.get('points') or []:
            method = entry.get('delivery_method') or {}
            point_id = method.get('map_point_id')
            point = stored.get(point_id)
            if point is None:
                continue
            point.name = (method.get('name') or '')[:500]
            point.address = (method.get('address') or '')[:1000]
            point.details = entry
            point.details_synced_at = now
            updated.append(point)

        if updated:
            OzonPickupPoint.objects.bulk_update(
                updated, ['name', 'address', 'details', 'details_synced_at']
            )

    return list(OzonPickupPoint.objects.filter(map_point_id__in=ids))
