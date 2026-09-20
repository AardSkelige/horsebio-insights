"""Возврат от Озона по заказу сайта, уехавшему со склада FBO.

Товар, лежащий на складе Ozon, в МойСкладе уже списан: поставку на FBO
оформляют заказом на контрагента «Озон» и отгрузкой по договору комиссии.
Когда такой товар уезжает нашему покупателю через Ozon Доставку, Озон его
как маркетплейс не продал — значит эту единицу надо у него забрать обратно,
и только потом отгружать покупателю.

Отсюда два документа на заказ: возврат покупателя «Озон» (здесь) и обычная
отгрузка покупателю, которую по статусу «Отгружен» создаёт сценарий МойСклада
(см. ms_orders). Без возврата отгрузка списала бы ту же единицу второй раз —
так уже вышло с заказом сайта №2095, разобранным руками 16.09.2026.

Возврат делаем **без основания**, то есть без ссылки на конкретную поставку.
Так решено 19.09.2026, после двух отказов МойСклада на живом документе: какая
именно единица уехала покупателю, знает только Озон — на его складе лежат наши
поставки вперемешку, и «наверное, из последней» раз за разом попадало то в
возвращённую поставку, то в отменённую. Себестоимость при этом не теряется:
её считает мастер МойСклада (`/wizard/salesreturn?action=evaluate_cost`) по
тому же FIFO. Поставку, из которой взята цена, пишем в комментарий — человеку.
"""

import logging

from ozon_logistics.models import OzonPosting
from ozon_logistics.services import ms_client
from ozon_logistics.services.ms_client import MoyskladError

logger = logging.getLogger(__name__)

# Статус возврата «Ушёл покупателю с FBO»: заведён 20.09.2026 специально под эти
# документы. Без него возврат выглядит как обычный — будто товар едет к нам на
# склад, — а он чисто учётный: товар уехал покупателю и на полки не ляжет.
STATE_ID = 'f350e80d-b4bb-11f1-0a80-05af0090c6ac'

# Контрагент «Озон»: им помечены поставки на склады Ozon и продажи маркетплейса.
AGENT_ID = '0bae2cd0-e446-11ee-0a80-0bdd011e453d'

# Статус заказа, которым помечают поставку на склад маркетплейса. Сам по себе он
# Озон не означает: в последних ста таких заказах 86 на Озон, 9 на Вайлдберриз,
# 5 на Яндекс Маркет — поэтому ищем по статусу И контрагенту сразу. Возврат по
# чужой поставке МойСклад отвергает («поле agent не соответствует полю
# связанного объекта»), и это выяснилось на живом документе 18.09.2026.
FBO_STATE_ID = '5b087787-9e6c-11ee-0a80-026a00112ccb'

# Сколько поставок просматриваем, разыскивая последнюю с нужным товаром.
# Поставки идут пачками по несколько раз в месяц, 200 хватает с запасом.
SUPPLY_PAGE_SIZE = 50
SUPPLY_PAGES = 4


class ReturnNotPossible(RuntimeError):
    """Возврат собрать не из чего — нужен человек."""


def _meta(entity, entity_id):
    return {'meta': {
        'href': f'{ms_client.BASE}/entity/{entity}/{entity_id}',
        'type': entity,
        'mediaType': 'application/json',
    }}


def fbo_products(postings):
    """Что именно уехало со склада Ozon: артикул → количество.

    Берём из ответа Ozon, сохранённого при отслеживании: там состав отправления
    с `offer_id` — это наши же артикулы из МойСклада.
    """
    totals = {}
    for posting in postings:
        if posting.schema != OzonPosting.SCHEMA_FBO:
            continue
        if posting.status in OzonPosting.ALARMING_STATUSES:
            continue  # отменённое отправление никуда не уехало
        for item in (posting.details or {}).get('products') or []:
            article = str(item.get('offer_id') or '').strip()
            quantity = float(item.get('quantity') or 0)
            if article and quantity > 0:
                totals[article] = totals.get(article, 0) + quantity
    return totals


def _supply_orders():
    """Заказы-поставки на склад Ozon, от свежих к старым."""
    for page in range(SUPPLY_PAGES):
        rows = ms_client.get('/entity/customerorder', [
            ('limit', SUPPLY_PAGE_SIZE),
            ('offset', page * SUPPLY_PAGE_SIZE),
            ('order', 'moment,desc'),
            ('expand', 'positions.assortment,organization,agent,contract,store'),
            ('filter',
             f'state={ms_client.BASE}/entity/customerorder/metadata/states/{FBO_STATE_ID}'
             f';agent={ms_client.BASE}/entity/counterparty/{AGENT_ID}'),
        ]).get('rows', [])
        if not rows:
            return
        yield from rows


class SupplyCache:
    """Страницы поставок читаем один раз на документ.

    Артикулов в заказе может быть несколько, а лимит запросов в МойСкладе общий
    на весь аккаунт: перечитывать одни и те же страницы на каждый товар незачем.
    Страницы тянем лениво — обычно ответ находится на первой.
    """

    def __init__(self):
        self._seen = []
        self._rest = _supply_orders()

    def __iter__(self):
        yield from self._seen
        for order in self._rest:
            self._seen.append(order)
            yield order


def find_supply_position(article, supplies=None):
    """Последняя поставка на Озон с этим товаром.

    Отсюда берём цену, НДС и реквизиты: по какой цене товар уходил на склад
    Озона, по такой же и возвращаем.
    """
    for order in (supplies if supplies is not None else SupplyCache()):
        for position in (order.get('positions') or {}).get('rows', []):
            assortment = position.get('assortment') or {}
            if (assortment.get('article') or '').strip() != article:
                continue
            return {
                'order_name': order.get('name'),
                'assortment': assortment,
                'price': position.get('price') or 0,
                'vat': position.get('vat') or 0,
                'vat_enabled': bool(position.get('vatEnabled')),
                'supply': order,
            }
    return None


def _with_costs(payload):
    """Себестоимость позиций считает мастер МойСклада — по тому же FIFO.

    Возврат без основания без неё встал бы с нулевой себестоимостью, и FIFO
    поехало бы: товар вернулся бы на склад бесплатным.
    """
    evaluated = ms_client.post('/wizard/salesreturn?action=evaluate_cost', payload)
    costs = [position.get('cost') for position in (evaluated.get('positions') or [])]
    if len(costs) != len(payload['positions']):
        raise ReturnNotPossible('МойСклад не посчитал себестоимость возврата')
    for position, cost in zip(payload['positions'], costs):
        if cost is None:
            raise ReturnNotPossible('МойСклад не посчитал себестоимость позиции')
        position['cost'] = cost
    return payload


def build_payload(products, *, site_order_id, order_number, posting_numbers):
    """Собирает возврат: позиции, реквизиты поставки и комментарий."""
    if not products:
        raise ReturnNotPossible('в отправлениях нет ни одной позиции с FBO')

    positions, sources, supply = [], [], None
    supplies = SupplyCache()
    for article, quantity in sorted(products.items()):
        found = find_supply_position(article, supplies)
        if found is None:
            raise ReturnNotPossible(
                f'не нашли поставку на Озон с товаром {article} — не с чего взять цену'
            )
        supply = supply or found['supply']
        positions.append({
            'assortment': {'meta': (found['assortment'].get('meta') or {})},
            'quantity': quantity,
            'price': found['price'],
            'vat': found['vat'],
            'vatEnabled': found['vat_enabled'],
        })
        sources.append(f"{article} × {quantity:g} — цена из поставки {found['order_name']}")

    description = '\n'.join([
        'Авто: товар уехал покупателю сайта через Ozon Доставку со склада FBO.',
        f'Заказ сайта №{site_order_id}, заказ Ozon {order_number}, '
        f'отправления {", ".join(posting_numbers)}.',
        'Озон эту единицу не продал — возвращаем её, чтобы отгрузка покупателю '
        'не списала товар второй раз.',
        *sources,
    ])

    # Организацию, контрагента, договор и склад берём из самой поставки: свои
    # константы рано или поздно разойдутся с жизнью — так и вышло на первой же
    # попытке, когда под статус «FBO» попала поставка на Яндекс Маркет.
    payload = {
        'applicable': True,
        'description': description,
        'positions': positions,
        'state': {'meta': {
            'href': f'{ms_client.BASE}/entity/salesreturn/metadata/states/{STATE_ID}',
            'type': 'state',
            'mediaType': 'application/json',
        }},
    }
    for field in ('organization', 'agent', 'contract', 'store'):
        meta = (supply.get(field) or {}).get('meta')
        if meta:
            payload[field] = {'meta': meta}
        elif field != 'contract':   # договор в заказе может и не стоять
            raise ReturnNotPossible(
                f'в поставке {supply.get("name")} нет поля «{field}» — возврат не собрать'
            )
    return _with_costs(payload)


def payload_for(quote, postings):
    """Возврат, который нужен этому заказу, — без похода на запись."""
    return build_payload(
        fbo_products(postings),
        site_order_id=quote.site_order_id,
        order_number=quote.order_number,
        posting_numbers=[p.posting_number for p in postings],
    )


def ensure_return(quote, postings, *, apply=True, payload=None):
    """Создаёт возврат от Озона, если его ещё нет. Возвращает имя документа.

    Повторный вызов ничего не делает: номер созданного документа лежит в
    расчёте, а второй возврат вернул бы товар, которого не было.
    """
    if quote.ms_return:
        return quote.ms_return

    payload = payload or payload_for(quote, postings)

    if not apply:
        logger.info('Ozon Доставка: создал бы возврат от Озона: %s', payload['description'])
        return '[dry-run]'

    created = ms_client.post('/entity/salesreturn', payload)
    name = created.get('name') or created.get('id') or ''
    logger.info(
        'Ozon Доставка: по заказу сайта %s создан возврат от Озона %s',
        quote.site_order_id, name,
    )
    return name


def return_failed(quote, exc):
    """Текст для человека: почему возврат не создался."""
    if isinstance(exc, ReturnNotPossible):
        return str(exc)
    if isinstance(exc, MoyskladError):
        return f'МойСклад отказал: {exc}'
    return str(exc)
