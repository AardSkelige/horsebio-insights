from collections import defaultdict

from django.core.cache import cache

from api.exceptions import ExternalServiceError
from msapi.client import get_json

STORE_NAME = 'Шатл - склад сырья + тары'
STORE_CACHE_KEY = 'raw_materials_store_id'
STORE_CACHE_TTL = 24 * 60 * 60


def store_id():
    cached = cache.get(STORE_CACHE_KEY)
    if cached:
        return cached
    rows = get_json('/entity/store', {'filter': f'name={STORE_NAME}', 'limit': 1}).get('rows', [])
    if not rows:
        raise ExternalServiceError(f'Склад «{STORE_NAME}» не найден в МойСклад')
    cache.set(STORE_CACHE_KEY, rows[0]['id'], STORE_CACHE_TTL)
    return rows[0]['id']


def slots(store):
    return {row['id']: row['name'] for row in get_json(f'/entity/store/{store}/slots', {'limit': 1000}).get('rows', [])}


def stock(store):
    rows = get_json('/report/stock/bystore/current', {'filter': f'storeId={store}', 'withRecalculate': 'true'})
    totals = {row['assortmentId']: row['stock'] for row in rows if row['stock'] is not None}
    recalculating = {row['assortmentId'] for row in rows if row['stock'] is None}
    return totals, recalculating


def main_slots(store):
    best = defaultdict(lambda: (None, 0))
    for row in get_json('/report/stock/byslot/current', {'filter': f'storeId={store}'}):
        if row['stock'] > best[row['assortmentId']][1]:
            best[row['assortmentId']] = (row['slotId'], row['stock'])
    return {assortment: slot for assortment, (slot, _) in best.items()}


def product(assortment_id):
    return get_json(f'/entity/product/{assortment_id}', {'expand': 'uom'})
