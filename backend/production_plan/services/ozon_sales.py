from calendar import monthrange
from collections import defaultdict

from django.db import transaction

from api.services import ozon_stock
from api.services.ozon_stock import READ_PAUSES, OzonStockError
from production_plan.models import OzonMonthSales
from production_plan.services.articles import normalize

PAGE = 1000


def _rows(data, key, path):
    rows = (data.get('result') or {}).get(key) if key else data.get('items')
    if rows is None:
        raise OzonStockError(f'Ozon прислал неожиданный ответ на {path}')
    return rows


def _ordered_by_sku(month, pauses):
    last_day = month.replace(day=monthrange(month.year, month.month)[1])
    result, offset = {}, 0
    while True:
        data = ozon_stock.read('/v1/analytics/data', {
            'date_from': month.isoformat(), 'date_to': last_day.isoformat(),
            'metrics': ['ordered_units', 'cancellations'], 'dimension': ['sku'], 'limit': PAGE, 'offset': offset,
        }, pauses)
        page = _rows(data, 'data', '/v1/analytics/data')
        for row in page:
            ordered, cancelled = row['metrics'][:2]
            result[int(row['dimensions'][0]['id'])] = max(int(ordered) - int(cancelled), 0)
        if len(page) < PAGE:
            return result
        offset += PAGE


def _offer_ids(skus, pauses):
    skus = sorted(skus)
    result = {}
    for start in range(0, len(skus), PAGE):
        data = ozon_stock.read('/v3/product/info/list', {'sku': [str(sku) for sku in skus[start:start + PAGE]]}, pauses)
        for item in _rows(data, None, '/v3/product/info/list'):
            for source in item.get('sources', []):
                result[int(source['sku'])] = item['offer_id']
            if item.get('sku'):
                result[int(item['sku'])] = item['offer_id']
    return result


def sync_month(month, pauses=READ_PAUSES):
    ordered = _ordered_by_sku(month, pauses)
    offers = _offer_ids(ordered, pauses)
    totals = defaultdict(int)
    for sku, quantity in ordered.items():
        if sku in offers:
            totals[normalize(offers[sku])] += quantity
    with transaction.atomic():
        OzonMonthSales.objects.filter(month=month).delete()
        OzonMonthSales.objects.bulk_create(
            OzonMonthSales(month=month, article=article, quantity=quantity)
            for article, quantity in totals.items() if quantity
        )
    return sum(totals.values())


def sync(months, pauses=READ_PAUSES):
    return {month: sync_month(month, pauses) for month in months}
