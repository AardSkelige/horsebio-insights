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

Возврат делаем **с основанием** — ссылкой на отгрузку той поставки, откуда
товар уехал. Тогда МойСклад сам возьмёт себестоимость нужной партии; возврат
без основания встал бы с нулевой себестоимостью и увёл бы FIFO.
"""

import logging

from ozon_logistics.models import OzonPosting
from ozon_logistics.services import ms_client
from ozon_logistics.services.ms_client import MoyskladError

logger = logging.getLogger(__name__)

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


def _load_demand(href):
    """Отгрузка целиком: и состав, и реквизиты.

    Реквизиты возврата берём из неё, а не из своих констант: МойСклад требует,
    чтобы у возврата с основанием совпадали организация, контрагент и договор,
    а поставки на разные юрлица идут с разными.
    """
    clean = href.split('?')[0]
    document = ms_client.get(
        f"/entity/demand/{clean.rsplit('/', 1)[-1]}",
        {'expand': 'positions.assortment,agent,organization,contract,store'},
    )
    # В ответе МойСклад повторяет ссылку запроса — вместе с ?expand=…, и она
    # уезжает в документ как есть. Возвращаем ссылку без параметров.
    document.setdefault('meta', {})['href'] = clean
    return document


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


def _demand_has(full, article):
    """Есть ли товар в этой отгрузке поставки.

    Поставку могут везти в несколько приёмов, и отгрузок у заказа тогда
    несколько. Основанием должна быть та, где товар действительно уехал:
    чужая отдаст себестоимость не той партии.
    """
    for position in (full.get('positions') or {}).get('rows', []):
        if ((position.get('assortment') or {}).get('article') or '').strip() == article:
            return True
    return False


def _basis_demand(demands, article):
    """Отгрузка-основание: единственная либо та, в которой есть этот товар."""
    hrefs = [((d.get('meta') or {}).get('href') or '') for d in demands]
    hrefs = [href for href in hrefs if href]
    if not hrefs:
        return None
    if len(hrefs) == 1:
        return _load_demand(hrefs[0])
    for href in reversed(hrefs):
        full = _load_demand(href)
        if _demand_has(full, article):
            return full
    return None


def _supply_orders():
    """Заказы-поставки на склад Ozon, от свежих к старым."""
    for page in range(SUPPLY_PAGES):
        rows = ms_client.get('/entity/customerorder', [
            ('limit', SUPPLY_PAGE_SIZE),
            ('offset', page * SUPPLY_PAGE_SIZE),
            ('order', 'moment,desc'),
            ('expand', 'positions.assortment,demands'),
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
    """Последняя поставка на FBO с этим товаром.

    Возвращает цену, НДС, товар и отгрузку-основание — всё, что нужно, чтобы
    возврат встал в ту же цену и ту же партию, что и поставка.
    """
    for order in (supplies if supplies is not None else SupplyCache()):
        for position in (order.get('positions') or {}).get('rows', []):
            assortment = position.get('assortment') or {}
            if (assortment.get('article') or '').strip() != article:
                continue
            demands = [d for d in (order.get('demands') or []) if isinstance(d, dict)]
            basis = _basis_demand(demands, article)
            if basis is None:
                # Поставку ещё не отвезли (или товар уехал не этой отгрузкой) —
                # возвращать пока не из чего, смотрим поставки дальше
                continue
            return {
                'order_name': order.get('name'),
                'assortment': assortment,
                'price': position.get('price') or 0,
                'vat': position.get('vat') or 0,
                'vat_enabled': bool(position.get('vatEnabled')),
                'demand': basis,
            }
    return None


def build_payload(products, *, site_order_id, order_number, posting_numbers):
    """Собирает возврат: позиции, основание и комментарий.

    Основание у всех позиций должно быть одно — МойСклад связывает возврат
    с одной отгрузкой. Если товары приехали разными поставками, возврат
    придётся делать человеку: молча свалить их в одну мы не имеем права.
    """
    if not products:
        raise ReturnNotPossible('в отправлениях нет ни одной позиции с FBO')

    positions, sources, bases = [], [], {}
    supplies = SupplyCache()
    for article, quantity in sorted(products.items()):
        found = find_supply_position(article, supplies)
        if found is None:
            raise ReturnNotPossible(
                f'не нашли поставку на FBO с товаром {article} — возвращать не из чего'
            )
        demand_href = ((found['demand'].get('meta') or {}).get('href') or '')
        if not demand_href:
            raise ReturnNotPossible(
                f'у поставки {found["order_name"]} нет ссылки на отгрузку — '
                'не к чему привязать возврат'
            )
        bases[demand_href] = found['demand']
        positions.append({
            'assortment': {'meta': (found['assortment'].get('meta') or {})},
            'quantity': quantity,
            'price': found['price'],
            'vat': found['vat'],
            'vatEnabled': found['vat_enabled'],
        })
        sources.append(f"{article} × {quantity:g} — из поставки {found['order_name']}")

    if len(bases) > 1:
        raise ReturnNotPossible(
            'товары уехали разными поставками, одним возвратом их не оформить'
        )
    demand_href, basis = next(iter(bases.items()))

    description = '\n'.join([
        'Авто: товар уехал покупателю сайта через Ozon Доставку со склада FBO.',
        f'Заказ сайта №{site_order_id}, заказ Ozon {order_number}, '
        f'отправления {", ".join(posting_numbers)}.',
        'Озон эту единицу не продал — возвращаем её, чтобы отгрузка покупателю '
        'не списала товар второй раз.',
        *sources,
    ])

    # Организацию, контрагента, договор и склад берём из отгрузки-основания:
    # МойСклад требует, чтобы они совпадали, а свои константы рано или поздно
    # разойдутся с жизнью — так и вышло на первой же попытке.
    payload = {
        'applicable': True,
        'description': description,
        'positions': positions,
        'demand': {'meta': {
            'href': demand_href, 'type': 'demand', 'mediaType': 'application/json',
        }},
    }
    for field in ('organization', 'agent', 'contract', 'store'):
        source = basis.get(field) or {}
        meta = source.get('meta')
        if meta:
            payload[field] = {'meta': meta}
        elif field != 'contract':   # договор в отгрузке может и не стоять
            raise ReturnNotPossible(
                f'в отгрузке-основании нет поля «{field}» — возврат не собрать'
            )
    return payload


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
