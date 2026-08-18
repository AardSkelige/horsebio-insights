#!/usr/bin/env python3
"""
Возвраты Ozon: единый источник данных для монитора и обогащения.

Почему отдельный модуль: в МойСкладе возвратов FBS нет как сущности — синхронизация
ведёт только заказ и отгрузку. Узнать, что покупатель что-то вернул, можно
исключительно из Ozon API. Раньше поход в /v1/returns/list был скопирован в
02_enrich_ozon_returns.py; теперь им пользуются оба скрипта.

Ключевые поля Ozon:
  place        — где коробка СЕЙЧАС (транзитный РФЦ, может быть любой)
  target_place — куда она едет В ИТОГЕ (наш ПВЗ или склад Озона)

Решение принимаем по target_place, но не раньше, чем возврат доедет до склада
Озона: пока статус «Ожидает отправки»/«Едет на склад Ozon», Озон ещё может
переназначить конечную точку на наш ПВЗ (так мы уже потеряли два документа —
заказы 06405 и 06469).
"""
import os
import re
from datetime import datetime, timedelta

import requests as _requests

from return_states import IN_TRANSIT, AT_PICKUP, AT_OUR_SITE, STUCK, GONE_TO_MP

OZON_RETURNS_URL = 'https://api-seller.ozon.ru/v1/returns/list'

# Наш ПВЗ: сюда Ozon свозит возвраты, которые мы физически забираем.
# Всё остальное (*_РФЦ_ВОЗВРАТЫ и пр.) — склады Озона.
OUR_PVZ = 'МО_ХИМКИ_96'

# Номер отправления Ozon в описании заказа: 43356677-1677-1 / 0112326660-1774-1
POSTING_RE = re.compile(r'(\d{6,}-\d{3,}-\d)')

# sys_name статусов Ozon, которые нам важны по смыслу
SYS_RECEIVED_BY_SELLER = 'ReceivedBySeller'   # отдан нам под роспись — товар у нас
SYS_RETURNED_TO_OZON = 'ReturnedToOzon'       # доехал до склада Озона — маршрут окончателен
SYS_DISPOSED = ('Disposed', 'Utilized')       # утилизирован/списан — не вернётся


def _ozon_headers() -> dict:
    client_id = os.getenv('OZON_CLIENT_ID', '')
    api_key = os.getenv('OZON_API_KEY', '')
    if not client_id or not api_key:
        raise SystemExit("Нет OZON_CLIENT_ID / OZON_API_KEY в окружении (.env)")
    return {'Client-Id': client_id, 'Api-Key': api_key, 'Content-Type': 'application/json'}


def fetch_returns(days_back: int = 240) -> list:
    """Возвраты Ozon за период — плоским списком нормализованных словарей."""
    headers = _ozon_headers()
    time_from = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%SZ')
    time_to = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')

    out, last_id = [], 0
    while True:
        body = {'filter': {'logistic_return_date': {'time_from': time_from, 'time_to': time_to}},
                'limit': 500, 'last_id': last_id}
        r = _requests.post(OZON_RETURNS_URL, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        rows = r.json().get('returns', [])
        if not rows:
            break
        for x in rows:
            if not x.get('posting_number'):
                continue
            out.append(_normalize(x))
        last_id = rows[-1]['id']
    return out


def _normalize(x: dict) -> dict:
    status = (x.get('visual') or {}).get('status', {})
    logistic = x.get('logistic') or {}
    product = x.get('product') or {}
    return {
        'ozon_id':     x.get('id'),
        'posting':     x.get('posting_number'),
        'schema':      x.get('schema', ''),
        'status':      status.get('display_name', ''),
        'sys':         status.get('sys_name', ''),
        'place':       (x.get('place') or {}).get('name', ''),
        'target':      (x.get('target_place') or {}).get('name', ''),
        'reason':      x.get('return_reason_name', ''),
        'product':     product.get('name', ''),
        'price_rub':   (product.get('price') or {}).get('price', 0),
        'return_date': (logistic.get('return_date') or '')[:10],   # когда возврат начался
        'received_at': (logistic.get('final_moment') or '')[:10],  # когда отдан нам
    }


def is_homeward(info: dict) -> bool:
    """Возврат едет к нам — документ в МС нужен."""
    return info.get('target') == OUR_PVZ


def is_at_our_site(info: dict) -> bool:
    """Ozon отдал коробку нам под роспись."""
    return info.get('sys') == SYS_RECEIVED_BY_SELLER


def is_route_final(info: dict) -> bool:
    """Маршрут больше не переиграется: возврат доехал до склада Озона или списан."""
    return info.get('sys') == SYS_RETURNED_TO_OZON or info.get('sys') in SYS_DISPOSED


def age_days(info: dict) -> int:
    """Сколько дней возврат в пути — от даты начала возврата в Ozon."""
    src = info.get('return_date') or ''
    try:
        return (datetime.now() - datetime.strptime(src, '%Y-%m-%d')).days
    except ValueError:
        return 0


def state_for(info: dict, warn_days: int = 30) -> str:
    """Имя статуса МС для одной записи возврата Ozon."""
    age = age_days(info)
    if is_homeward(info):
        if is_at_our_site(info):
            return AT_OUR_SITE
        if age >= warn_days:
            return STUCK
        # Коробка физически уже в нашем ПВЗ, но нам её ещё не выдали — значит
        # лежит и ждёт, пока приедут. Отдельное действие и отдельный человек,
        # поэтому не смешиваем с «едет». Определяем по месту, а не по названию
        # статуса: place — то, что Ozon знает точно, названия он меняет.
        if info.get('place') == OUR_PVZ:
            return AT_PICKUP
        return IN_TRANSIT
    # Едет на склад маркетплейса. Пока не доехал, конечная точка ещё может
    # смениться на наш ПВЗ — держим черновик, потерять документ дороже. Но окно
    # на переигровку конечное: за warn_days Озон определяется окончательно,
    # иначе черновики «Ожидает отправки» висели бы годами.
    if is_route_final(info) or age >= warn_days:
        return GONE_TO_MP
    return IN_TRANSIT


# Чем меньше число, тем важнее статус: на один posting_number Ozon может завести
# несколько возвратов (частичный возврат — часть коробок уже у нас, часть в пути).
_STATE_PRIORITY = {AT_PICKUP: 0, AT_OUR_SITE: 1, STUCK: 2, IN_TRANSIT: 3, GONE_TO_MP: 4}


def state_for_group(infos: list, warn_days: int = 30) -> str:
    """Статус для отправления целиком — по самой срочной из его записей."""
    return min((state_for(i, warn_days) for i in infos),
               key=lambda s: _STATE_PRIORITY.get(s, 9))


def is_draft_dead(infos: list, warn_days: int = 30) -> bool:
    """Черновик можно удалять: товар к нам не приедет и это уже не изменится.

    Два условия сразу, и оба обязательны:
      • возврат доехал до склада Озона (или списан) — маршрут окончателен;
      • с начала возврата прошло warn_days — окно на переигровку закрыто.

    Ровно этого не хватало прежней версии: она удаляла черновик по одному только
    target_place, на второй день после отмены, когда Озон ещё показывал
    промежуточный склад. Так потерялись документы по заказам 06405 и 06469.
    """
    if state_for_group(infos, warn_days) != GONE_TO_MP:
        return False
    age = max(age_days(i) for i in infos)
    if all(is_route_final(i) for i in infos) and age >= warn_days:
        return True
    # Возврат может застрять в «Ожидает отправки» на своём складе и не доехать до
    # финального статуса никогда (видели такие по 200+ дней). Держать из-за этого
    # вечный черновик незачем: два срока ожидания — и закрываем.
    return age >= 2 * warn_days


def posting_from_text(text: str) -> str | None:
    """Номер отправления Ozon из описания заказа/возврата."""
    m = POSTING_RE.search(text or '')
    return m.group(1) if m else None


# ─── Интерфейс источника для returns_enrich.py ────────────────────────────────
LABEL = 'Ozon'
AGENT_NAMES = ('Озон',)
MARK = ' · Ozon:'
ORDER_MARK = '\n↩ Возврат на склад Ozon:'


def fetch_map(days_back: int = 240) -> dict:
    """posting_number → список записей возврата."""
    out = {}
    for info in fetch_returns(days_back):
        out.setdefault(info['posting'], []).append(info)
    return out


def key_from_order(order: dict) -> str | None:
    """Ключ сопоставления — номер отправления Ozon из описания заказа."""
    return posting_from_text(order.get('description'))


def describe(infos: list) -> str:
    """Хвост описания документа: где коробка и с какого числа."""
    head = infos[0]
    where = (head['place'] or '—')[:34]
    since = f" · с {head['return_date']}" if head['return_date'] else ''
    return f" {head['status']} [{where}]{since} · {age_days(head)} дн"


def order_note(infos: list) -> str:
    """Хвост пометки в заказе, когда черновик удаляется."""
    head = infos[0]
    return f" {head['target']} · {head['status']}"


def info_key(info: dict) -> str:
    """Ключ группировки — номер отправления."""
    return info['posting']


def needs_document(info: dict) -> bool:
    """Нужен ли документ возврата: FBS и едет к нам (ФБО ведёт Лера сборными)."""
    return info.get('schema') == 'Fbs' and is_homeward(info)


def order_filter(key: str) -> str:
    """Фильтр МС для поиска заказа по номеру отправления."""
    return f'description~{key}'


def draft_note(key: str, infos: list) -> str:
    """Чем объяснить возврат в описании создаваемого черновика."""
    return f"возврат Ozon {key}: {infos[0]['reason']}"
