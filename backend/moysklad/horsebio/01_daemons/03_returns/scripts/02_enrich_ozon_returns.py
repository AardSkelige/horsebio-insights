#!/usr/bin/env python3
"""
Обогащение черновиков возвратов Озон реальным статусом с Ozon API.

Монитор (01_monitor_returns.py) создаёт черновик возврата, когда заказ Озон
уходит в «Отменен/Возврат». Но физически товар при этом чаще всего едет НЕ к нам,
а на склад Озона — и Лера справедливо не может его провести. Раньше это было не
видно: черновик просто висел.

Этот скрипт для каждого черновика Озон подтягивает через Ozon API (/v1/returns/list)
реальный статус и место товара и дописывает их в комментарий возврата в МойСклад.
Так и Лера в МС, и проверки в Инсайте видят, где возврат и что с ним делать:
  • Получен продавцом      → товар у нас, можно проводить
  • Едет к нам             → скоро у нас, ждать
  • На складе Ozon / Ожидает отправки / Едет на склад Ozon → у Озона, ждать
  • Утилизация / списание   → товар не придёт, черновик можно удалить

Матчинг: возврат → отгрузка → заказ → номер отправления Ozon (в описании заказа)
↔ posting_number в API. Надёжно, без коллизий по номеру заказа.

Запуск:
  python3 02_enrich_ozon_returns.py            # обновить комментарии в МС
  python3 02_enrich_ozon_returns.py --dry-run  # показать, ничего не писать
"""
import os
import re
import sys
import time
import argparse
import requests as _requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import MOYSKLAD_TOKEN, BASE_URL  # noqa: E402  (грузит backend/.env, включая OZON_*)

MS_HEADERS = {
    'Authorization': f'Bearer {MOYSKLAD_TOKEN}',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/json',
}
OZON_HEADERS = {
    'Client-Id': os.getenv('OZON_CLIENT_ID', ''),
    'Api-Key':   os.getenv('OZON_API_KEY', ''),
    'Content-Type': 'application/json',
}
OZON_RETURNS_URL = 'https://api-seller.ozon.ru/v1/returns/list'

# Маркер, с которого начинается наш блок статуса в описании (для идемпотентной замены)
MARK = ' · Ozon:'
# Номер отправления Ozon в описании заказа: 43356677-1677-1 / 0112326660-1774-1
POSTING_RE = re.compile(r'(\d{6,}-\d{3,}-\d)')

# Классификация статусов Ozon → действие
def classify(sys_name: str, display: str) -> str:
    s = (sys_name or '').lower()
    d = (display or '').lower()
    if s == 'receivedbyseller' or 'получен продавц' in d:
        return 'у нас'            # товар у продавца → проверить/провести
    if 'утилиз' in d or 'списан' in d or 'dispos' in s or 'utiliz' in s:
        return 'не придёт'        # товар не вернётся → черновик можно удалить
    if 'едет к' in d or 'movingtoseller' in s:
        return 'едет к нам'
    return 'у Ozon'              # На складе Ozon / Ожидает отправки / Едет на склад Ozon


def build_ozon_map(months_back: int = 8) -> dict:
    """posting_number → {status, sys, place, schema, action}. Возвраты за последние N мес."""
    if not OZON_HEADERS['Client-Id'] or not OZON_HEADERS['Api-Key']:
        raise SystemExit("Нет OZON_CLIENT_ID / OZON_API_KEY в окружении (.env)")
    time_from = (datetime.utcnow() - timedelta(days=months_back * 30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    time_to = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    omap = {}
    last_id = 0
    while True:
        body = {'filter': {'logistic_return_date': {'time_from': time_from, 'time_to': time_to}},
                'limit': 500, 'last_id': last_id}
        r = _requests.post(OZON_RETURNS_URL, headers=OZON_HEADERS, json=body, timeout=60)
        r.raise_for_status()
        rows = r.json().get('returns', [])
        if not rows:
            break
        for x in rows:
            pn = x.get('posting_number')
            if not pn:
                continue
            st = (x.get('visual') or {}).get('status', {})
            display = st.get('display_name', '')
            omap[pn] = {
                'status': display,
                'sys': st.get('sys_name', ''),
                'place': (x.get('place') or {}).get('name', ''),
                'schema': x.get('schema', ''),
                'action': classify(st.get('sys_name', ''), display),
            }
        last_id = rows[-1]['id']
    return omap


def fetch_ozon_drafts() -> list:
    """Непроведённые возвраты Озон с раскрытыми отгрузкой и заказом."""
    docs = []
    offset = 0
    while True:
        r = _requests.get(f'{BASE_URL}/entity/salesreturn', headers=MS_HEADERS, params={
            'filter': 'applicable=false',
            'expand': 'demand.customerOrder,agent',
            'limit': 100, 'offset': offset,
        }, timeout=40)
        r.raise_for_status()
        rows = r.json().get('rows', [])
        docs.extend(rows)
        if len(rows) < 100:
            break
        offset += 100
    return [d for d in docs if (d.get('agent') or {}).get('name') == 'Озон']


def posting_from_return(doc: dict) -> str | None:
    """Номер отправления Ozon из описания связанного заказа."""
    co = (doc.get('demand') or {}).get('customerOrder') or {}
    m = POSTING_RE.search(co.get('description') or '')
    return m.group(1) if m else None


def build_description(base_desc: str, info: dict) -> str:
    """Идемпотентно заменить/добавить блок статуса Ozon в описании."""
    base = base_desc.split(MARK)[0].rstrip()
    place = (info['place'] or '')[:34]
    return f"{base}{MARK} {info['status']} [{place}] → {info['action']} · {datetime.now():%d.%m}"


def main():
    ap = argparse.ArgumentParser(description="Обогащение возвратов Озон статусом с Ozon API")
    ap.add_argument('--dry-run', action='store_true', help="Показать, ничего не писать в МС")
    args = ap.parse_args()

    print(f"{'='*64}\nОбогащение возвратов Озон: {datetime.now():%Y-%m-%d %H:%M:%S}")
    if args.dry_run:
        print("[DRY-RUN — комментарии НЕ пишутся]")
    print('='*64)

    omap = build_ozon_map()
    print(f"Ozon-возвратов в карте: {len(omap)}")

    drafts = fetch_ozon_drafts()
    print(f"Черновиков Озон в МС: {len(drafts)}\n")

    counts = {'updated': 0, 'unchanged': 0, 'no_posting': 0, 'no_ozon_match': 0, 'error': 0}
    by_action = {'у нас': [], 'едет к нам': [], 'у Ozon': [], 'не придёт': []}

    for d in drafts:
        name = d.get('name', '?')
        pn = posting_from_return(d)
        if not pn:
            counts['no_posting'] += 1
            print(f"  SKIP {name}: не нашёл номер отправления (ручной/ФБО?)")
            continue
        info = omap.get(pn)
        if not info:
            counts['no_ozon_match'] += 1
            print(f"  WARN {name}: {pn} нет в Ozon API (старый/за окном)")
            continue

        by_action[info['action']].append(name)
        new_desc = build_description(d.get('description') or '', info)
        if new_desc == (d.get('description') or ''):
            counts['unchanged'] += 1
            continue

        print(f"  {name} → {info['status']:22} @ {info['place']:28} → {info['action']}")
        if args.dry_run:
            counts['updated'] += 1
            continue
        try:
            resp = _requests.put(f"{BASE_URL}/entity/salesreturn/{d['id']}",
                                 headers=MS_HEADERS, json={'description': new_desc}, timeout=30)
            if resp.status_code == 200:
                counts['updated'] += 1
            else:
                counts['error'] += 1
                print(f"    ERROR {resp.status_code}: {resp.text[:120]}")
            time.sleep(0.15)
        except Exception as e:
            counts['error'] += 1
            print(f"    ERROR: {e}")

    print(f"\n{'='*64}\nИтого:")
    print(f"  Обновлено комментариев:  {counts['updated']}")
    print(f"  Без изменений:           {counts['unchanged']}")
    print(f"  Нет номера отправления:  {counts['no_posting']}")
    print(f"  Нет в Ozon API:          {counts['no_ozon_match']}")
    print(f"  Ошибки:                  {counts['error']}")
    print(f"\n  По действию:")
    print(f"    🟢 у нас (провести):    {len(by_action['у нас'])}  {by_action['у нас']}")
    print(f"    🟡 едет к нам:          {len(by_action['едет к нам'])}  {by_action['едет к нам']}")
    print(f"    ⚪ у Ozon (ждать):      {len(by_action['у Ozon'])}")
    print(f"    🔴 не придёт (удалить): {len(by_action['не придёт'])}  {by_action['не придёт']}")
    print('='*64)


if __name__ == '__main__':
    main()
