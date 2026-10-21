import hashlib
import logging
from collections import defaultdict

import requests
from django.core.cache import cache

from api.exceptions import ExternalServiceError
from msapi.client import BASE_URL, delete, get_json, post_json

STORE_NAME = 'Шатл - склад сырья + тары'
PRODUCTION_STORE_NAME = 'Склад производства + обклейки'
ORGANIZATION_NAME = 'ООО "ФАРМПРОТЕКТ"'
CACHE_TTL = 24 * 60 * 60
PAGE = 100

logger = logging.getLogger(__name__)


def _id_by_name(entity, name):
    key = f'raw_materials_{entity}_id:{hashlib.md5(name.encode()).hexdigest()}'
    cached = cache.get(key)
    if cached:
        return cached
    rows = get_json(f'/entity/{entity}', {'filter': f'name={name}', 'limit': 1}).get('rows', [])
    if not rows:
        raise ExternalServiceError(f'«{name}» не найден в МойСклад')
    cache.set(key, rows[0]['id'], CACHE_TTL)
    return rows[0]['id']


def store_id():
    return _id_by_name('store', STORE_NAME)


def _meta(path, kind):
    return {'meta': {'href': f'{BASE_URL}{path}', 'type': kind, 'mediaType': 'application/json'}}


def slots(store):
    return {row['id']: row['name'] for row in get_json(f'/entity/store/{store}/slots', {'limit': 1000}).get('rows', [])}


def stock(store):
    rows = get_json('/report/stock/bystore/current', {'filter': f'storeId={store}', 'withRecalculate': 'true'})
    totals = {row['assortmentId']: row['stock'] for row in rows if row['stock'] is not None}
    recalculating = {row['assortmentId'] for row in rows if row['stock'] is None}
    return totals, recalculating


def slot_stock(store):
    placed = defaultdict(dict)
    for row in get_json('/report/stock/byslot/current', {'filter': f'storeId={store}'}):
        if row['stock'] > 0:
            placed[row['assortmentId']][row['slotId']] = row['stock']
    return dict(placed)


def supplies(store, since):
    rows, offset = [], 0
    while True:
        page = get_json('/entity/supply', {
            'filter': f'store={BASE_URL}/entity/store/{store};moment>={since:%Y-%m-%d %H:%M:%S}',
            'expand': 'agent,positions',
            'order': 'moment,desc',
            'limit': PAGE,
            'offset': offset,
        }).get('rows', [])
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        offset += PAGE


def product(assortment_id):
    return get_json(f'/entity/product/{assortment_id}', {'expand': 'uom'})


def _buy_price(product_id):
    return (product(product_id).get('buyPrice') or {}).get('value', 0)


def create_move(external_code, description, positions):
    source = store_id()
    prices = {product: _buy_price(product) for product, _, _ in positions}
    rows = [
        {
            'quantity': float(quantity),
            'price': prices[product],
            'assortment': _meta(f'/entity/product/{product}', 'product'),
            **({'sourceSlot': _meta(f'/entity/store/{source}/slots/{slot}', 'slot')} if slot else {}),
        }
        for product, slot, quantity in positions
    ]
    try:
        move = post_json('/entity/move', {
            'organization': _meta(f"/entity/organization/{_id_by_name('organization', ORGANIZATION_NAME)}", 'organization'),
            'sourceStore': _meta(f'/entity/store/{source}', 'store'),
            'targetStore': _meta(f"/entity/store/{_id_by_name('store', PRODUCTION_STORE_NAME)}", 'store'),
            'externalCode': external_code,
            'description': description,
            'applicable': True,
            'positions': rows,
        })
    except requests.RequestException:
        _drop_moves(external_code)
        raise
    _drop_moves(external_code, keep=move['id'])
    return move


def discard_move(move_id):
    try:
        delete(f'/entity/move/{move_id}')
    except requests.RequestException:
        logger.exception('Не удалось удалить перемещение %s в МойСклад', move_id)


def _drop_moves(external_code, keep=None):
    try:
        rows = get_json('/entity/move', {'filter': f'externalCode={external_code}'}).get('rows', [])
    except requests.RequestException:
        logger.exception('Не удалось проверить повторы перемещения %s', external_code)
        return
    for row in rows:
        if row['id'] != keep:
            discard_move(row['id'])
