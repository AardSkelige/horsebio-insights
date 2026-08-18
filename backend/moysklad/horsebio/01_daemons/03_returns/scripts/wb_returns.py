#!/usr/bin/env python3
"""
Возвраты Вайлдберриз: источник данных для статусов черновиков.

Долгое время считалось, что из API ВБ маршрут возврата не достать и остаётся
верить, что «всё доезжало». Это уже не так: отчёт /api/v1/analytics/goods-return
отдаёт по каждому возврату физический статус, адрес пункта выдачи и даты — то же
самое, что Ozon отдаёт в /v1/returns/list.

Сопоставление с МойСкладом прямое: в отчёте есть orderId — это «Номер задания в
Wildberries», который синхронизация уже пишет в описание заказа.

В отличие от Озона, у ВБ нет ветки «возврат осел на складе маркетплейса»: всё,
что вернули, едет к нам в ПВЗ. Поэтому мёртвых черновиков тут не бывает.
"""
import os
import re
import time
from datetime import datetime, timedelta

import requests as _requests

from return_states import IN_TRANSIT, AT_PICKUP, AT_OUR_SITE, STUCK

GOODS_RETURN_URL = 'https://seller-analytics-api.wildberries.ru/api/v1/analytics/goods-return'

# Отчёт отдаётся окнами не больше 31 дня — ходим несколькими запросами.
WINDOW_DAYS = 30

# Насколько глубоко имеет смысл спрашивать ВБ. Каждое лишнее окно — до
# полуминуты ожидания после 429, а возвраты старше трёх месяцев уже закрыты.
MAX_DAYS_BACK = 90

# Номер задания ВБ в описании заказа МС
TASK_RE = re.compile(r'Номер задания в Wildberries:\s*(\d+)')

# Статусы отчёта ВБ
ST_ISSUED = 'Выдано'                          # выдали нам в ПВЗ — товар у нас
ST_TO_PICKUP = 'В пути в пвз'                 # едет в пункт выдачи
ST_EXPIRED = 'Истек срок хранения на пвз'     # не забрали вовремя
ST_UNKNOWN = 'Статус не определен'


def _headers() -> dict:
    token = os.getenv('WB_API_TOKEN', '')
    if not token:
        raise SystemExit("Нет WB_API_TOKEN в окружении (.env)")
    return {'Authorization': token, 'Content-Type': 'application/json'}


def fetch_returns(days_back: int = 90) -> list:
    """Строки отчёта возвратов ВБ за период, нормализованные.

    Глубину держим небольшой намеренно: ВБ отдаёт отчёт окнами максимум по 31 дню
    и жёстко лимитирует запросы — на каждое лишнее окно уходит до полуминуты
    ожидания после 429. Черновики возвратов столько не живут: самый старый у нас
    был 72 дня, обычные закрываются за пару недель.
    """
    headers = _headers()
    seen, out = set(), []
    windows = list(range(0, days_back, WINDOW_DAYS))
    for i, back in enumerate(windows, 1):
        date_from = (datetime.now() - timedelta(days=back + WINDOW_DAYS)).strftime('%Y-%m-%d')
        date_to = (datetime.now() - timedelta(days=back)).strftime('%Y-%m-%d')
        print(f"  окно {i}/{len(windows)}: {date_from}…{date_to}", flush=True)
        rows = _get_window(headers, date_from, date_to)
        for x in rows:
            key = (x.get('orderId'), x.get('shkId'))
            if key in seen:
                continue
            seen.add(key)
            out.append(_normalize(x))
        time.sleep(1)
    return out


def _get_window(headers: dict, date_from: str, date_to: str, tries: int = 4) -> list:
    """Одно окно отчёта. ВБ щедр на 429 — уважаем лимит и ждём."""
    for attempt in range(1, tries + 1):
        r = _requests.get(GOODS_RETURN_URL, headers=headers,
                          params={'dateFrom': date_from, 'dateTo': date_to}, timeout=120)
        if r.status_code == 429:
            wait = int(r.headers.get('X-Ratelimit-Retry', 20)) + 2
            print(f"    лимит ВБ, ждём {wait}с (попытка {attempt}/{tries})", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        body = r.json()
        return (body.get('report') if isinstance(body, dict) else body) or []
    print(f"    окно {date_from}…{date_to} пропущено: ВБ так и не ответил", flush=True)
    return []


def _normalize(x: dict) -> dict:
    return {
        'order_id':    x.get('orderId'),
        'shk_id':      x.get('shkId'),
        'sticker_id':  x.get('stickerId', ''),
        'srid':        x.get('srid', ''),
        'nm_id':       x.get('nmId'),          # артикул ВБ — по нему ищется карточка
        'status':      x.get('status', ''),
        'return_type': x.get('returnType', ''),
        'office':      x.get('dstOfficeAddress', ''),
        'product':     x.get('subjectName', ''),
        'barcode':     x.get('barcode', ''),
        'return_date': (x.get('orderDt') or '')[:10],       # когда возврат начался
        'ready_at':    (x.get('readyToReturnDt') or '')[:10],  # приехал в ПВЗ
        'issued_at':   (x.get('completedDt') or '')[:10],   # выдан нам
        'expired_at':  (x.get('expiredDt') or '')[:10],
    }


def age_days(info: dict) -> int:
    """Сколько дней идёт возврат — от даты заказа, с которого он начался."""
    try:
        return (datetime.now() - datetime.strptime(info.get('return_date') or '', '%Y-%m-%d')).days
    except ValueError:
        return 0


def is_at_pickup(info: dict) -> bool:
    """Коробка доехала до пункта выдачи, но нам её ещё не отдали.

    ВБ отдельного статуса для этого не заводит, но проставляет readyToReturnDt в
    момент прибытия и completedDt в момент выдачи. Разрыв между ними и есть
    «лежит и ждёт» — то самое состояние, в котором сгорел 21 вывоз на ДПК
    Октябрьский.
    """
    return bool(info.get('ready_at')) and not info.get('issued_at')


def state_for(info: dict, warn_days: int = 30) -> str:
    """Имя статуса МС для одной строки отчёта ВБ."""
    status = info.get('status', '')
    if status == ST_ISSUED:
        return AT_OUR_SITE
    if status == ST_EXPIRED:
        # Не забрали вовремя — товар, скорее всего, потерян. Разбираться людям.
        return STUCK
    if is_at_pickup(info):
        return AT_PICKUP
    return STUCK if age_days(info) >= warn_days else IN_TRANSIT


_STATE_PRIORITY = {AT_PICKUP: 0, AT_OUR_SITE: 1, STUCK: 2, IN_TRANSIT: 3}


def state_for_group(infos: list, warn_days: int = 30) -> str:
    """Статус для задания целиком — по самой срочной из его строк."""
    return min((state_for(i, warn_days) for i in infos),
               key=lambda s: _STATE_PRIORITY.get(s, 9))


def is_draft_dead(infos: list, warn_days: int = 30) -> bool:
    """У ВБ возвраты всегда едут к нам — удалять черновики не за что."""
    return False


# ─── Интерфейс источника для returns_enrich.py ────────────────────────────────
LABEL = 'ВБ'
AGENT_NAMES = ('Вайлдберриз (Вб)', 'Вб Вайлдберриз')
MARK = ' · ВБ:'
ORDER_MARK = '\n↩ Возврат ВБ:'


def fetch_map(days_back: int = 210) -> dict:
    """Номер задания ВБ → список строк отчёта."""
    out = {}
    for info in fetch_returns(days_back):
        if info['order_id']:
            out.setdefault(str(info['order_id']), []).append(info)
    return out


def key_from_order(order: dict) -> str | None:
    """Ключ сопоставления — номер задания ВБ из описания заказа."""
    m = TASK_RE.search(order.get('description') or '')
    return m.group(1) if m else None


def describe(infos: list) -> str:
    head = infos[0]
    where = (head['office'] or '—')[:34]
    since = f" · с {head['return_date']}" if head['return_date'] else ''
    return f" {head['status']} [{where}]{since} · {age_days(head)} дн"


def order_note(infos: list) -> str:
    head = infos[0]
    return f" {head['office']} · {head['status']}"


# Возврат покупателя. Второй тип — «Возврат по инициативе продавца» — это наши
# вывозы со склада ВБ: покупателя там нет, документ возврата не нужен, товар
# приходует Лера приёмкой, когда его физически привезут.
CUSTOMER_RETURN = 'приехал по МП'


def info_key(info: dict) -> str:
    """Ключ группировки — номер задания ВБ."""
    return str(info['order_id'])


def needs_document(info: dict) -> bool:
    """Нужен ли документ: возврат покупателя, привязанный к заданию."""
    return bool(info.get('order_id')) and CUSTOMER_RETURN in (info.get('return_type') or '')


def order_filter(key: str) -> str:
    """Фильтр МС для поиска заказа по номеру задания ВБ.

    Ищем вместе со словом Wildberries: голый номер задания встречается
    в описаниях и в других ролях, а так совпадение однозначно.
    """
    return f'description~Wildberries: {key}'


def draft_note(key: str, infos: list) -> str:
    return f"возврат ВБ, задание {key}: {infos[0]['status']}"
