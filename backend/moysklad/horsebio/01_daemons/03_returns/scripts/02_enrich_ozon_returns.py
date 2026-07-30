#!/usr/bin/env python3
"""
Обогащение черновиков возвратов Озон реальным статусом с Ozon API.

Монитор (01_monitor_returns.py) создаёт черновик возврата, когда заказ Озон
уходит в «Отменен/Возврат». Но физически товар при этом чаще всего едет НЕ к нам,
а на склад Озона — и Лера справедливо не может его провести. Раньше это было не
видно: черновик просто висел.

Этот скрипт для каждого черновика Озон подтягивает через Ozon API (/v1/returns/list)
реальный статус, конечный пункт назначения (target_place) и место товара.

Ключевое решение — по target_place (КОНЕЧНЫЙ пункт, не транзитный place):
  • target_place == МО_ХИМКИ_96 (наш ПВЗ) → товар приедет к нам, мы его заберём,
    документ возврата нужен. Оставляем черновик и дописываем статус в комментарий:
      – Получен продавцом → товар у нас, можно проводить
      – Едет к нам        → скоро у нас, ждать
  • target_place == любой *_РФЦ_ВОЗВРАТЫ (склад Озона) → товар к нам НЕ приедет,
    документ возврата не нужен. Удаляем черновик и пишем пометку в самом заказе
    (куда уехал возврат), чтобы это было видно в МС.

Берём именно target_place, а не place: place — где товар сейчас (транзитный РФЦ,
товар может оказаться рядом проездом), target_place — куда он в итоге едет.

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
# Маркер пометки в описании ЗАКАЗА (не возврата), что возврат ушёл на склад Ozon
ORDER_MARK = '\n↩ Возврат на склад Ozon:'
# Наш ПВЗ: сюда Ozon свозит возвраты, которые мы физически забираем. Всё остальное
# (*_РФЦ_ВОЗВРАТЫ) — склады Озона, куда товар уезжает и к нам не попадает.
OUR_PVZ = 'МО_ХИМКИ_96'
# Номер отправления Ozon в описании заказа: 43356677-1677-1 / 0112326660-1774-1
POSTING_RE = re.compile(r'(\d{6,}-\d{3,}-\d)')

# Классификация статусов Ozon → где товar (НЕ команда проводить — это решает Лера,
# когда коробка физически придёт к нам на склад в Подрезково; Ozon этого не знает).
def classify(sys_name: str, display: str) -> str:
    s = (sys_name or '').lower()
    d = (display or '').lower()
    if 'утилиз' in d or 'списан' in d or 'dispos' in s or 'utiliz' in s:
        return 'не придёт'        # утилизирован/списан → товар не вернётся, черновик удалить
    if 'едет' in d and ('вам' in d or 'продавц' in d) or 'movingtoseller' in s:
        return 'едет к нам'       # реально едет к продавцу → ждать поступление
    if s == 'receivedbyseller' or 'получен' in d:
        return 'получен — уточнить'  # Ozon пишет «получен», но место может быть его склад/ПВЗ
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
                'target': (x.get('target_place') or {}).get('name', ''),
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


def build_order_note(base_desc: str, info: dict) -> str:
    """Идемпотентно добавить в описание ЗАКАЗА пометку, что возврат ушёл на склад Ozon."""
    base = base_desc.split(ORDER_MARK)[0].rstrip()
    return f"{base}{ORDER_MARK} {info['target']} · {info['status']} · {datetime.now():%d.%m}"


def _export_results(counts, by_action, deleted_details, error_details, path):
    """Структурированный JSON для страницы /checks: стат-карточки + раскрываемые списки."""
    import json as _json
    from datetime import datetime as _dt

    received = by_action.get('получен — уточнить', [])  # в Химки/у нас — можно проводить
    coming = by_action.get('едет к нам', [])
    dl, er = counts.get('deleted', 0), counts.get('error', 0)

    stats = [
        {"label": "Удалено (ушли к Ozon)", "value": dl, "tone": "ok" if dl else "neutral",
         **({"cat": "deleted"} if dl else {})},
        {"label": "Можно проводить", "value": len(received), "tone": "warning" if received else "neutral",
         **({"cat": "received"} if received else {})},
        {"label": "Едут к нам", "value": len(coming), "tone": "neutral"},
        {"label": "Обновлены комменты", "value": counts.get("updated", 0), "tone": "neutral"},
        {"label": "Ошибки", "value": er, "tone": "critical" if er else "neutral",
         **({"cat": "errors"} if er else {})},
    ]

    categories = []
    if error_details:
        categories.append({"key": "errors", "title": "Ошибки", "severity": "critical",
            "kind": None, "ms_type": None, "count": len(error_details),
            "items": [{"key": "", "ms_id": "", "object": e["obj"], "severity": "critical", "detail": e["msg"]}
                      for e in error_details]})
    if received:
        categories.append({"key": "received", "title": "Возврат у нас — можно проводить", "severity": "important",
            "kind": None, "ms_type": None, "count": len(received),
            "items": [{"key": "", "ms_id": "", "object": f"Возврат {n}", "severity": "important",
                       "detail": "получен, проверить и провести"} for n in received]})
    if deleted_details:
        categories.append({"key": "deleted", "title": "Удалены — уехали на склад Ozon", "severity": "ok",
            "kind": None, "ms_type": None, "count": len(deleted_details),
            "items": [{"key": "", "ms_id": "", "object": f"Заказ №{d['order']}", "severity": "ok",
                       "detail": f"{d['target']} · {d['status']}"} for d in deleted_details]})

    payload = {
        "generated_at": _dt.now().isoformat(timespec="seconds"), "params": {},
        "summary": {"critical": er, "important": len(received), "warnings": 0,
                    "ok": dl, "stats": stats},
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="Обогащение возвратов Озон статусом с Ozon API")
    ap.add_argument('--dry-run', action='store_true', help="Показать, ничего не писать в МС")
    ap.add_argument('--results-out', type=str, default=None,
                    help="Путь для структурированного JSON находок (для страницы /checks)")
    args = ap.parse_args()

    print(f"{'='*64}\nОбогащение возвратов Озон: {datetime.now():%Y-%m-%d %H:%M:%S}")
    if args.dry_run:
        print("[DRY-RUN — комментарии НЕ пишутся]")
    print('='*64)

    omap = build_ozon_map()
    print(f"Ozon-возвратов в карте: {len(omap)}")

    drafts = fetch_ozon_drafts()
    print(f"Черновиков Озон в МС: {len(drafts)}\n")

    counts = {'updated': 0, 'unchanged': 0, 'deleted': 0, 'no_posting': 0, 'no_ozon_match': 0, 'error': 0}
    by_action = {'получен — уточнить': [], 'едет к нам': [], 'у Ozon': [], 'не придёт': []}
    deleted_details = []   # {order, target, status} — уехали на склад Ozon, черновик удалён
    error_details = []     # {obj, msg}

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

        # Конечный пункт — склад Озона (не наш ПВЗ): товар к нам не приедет,
        # документ возврата не нужен. Помечаем заказ и удаляем черновик.
        # target пустой = Ozon ещё не назначил маршрут → решение откладываем (оставляем).
        target = info.get('target', '')
        if target and target != OUR_PVZ:
            co = (d.get('demand') or {}).get('customerOrder') or {}
            note = build_order_note(co.get('description') or '', info)
            print(f"  DEL  {name}: возврат → {target} ({info['status']}) — "
                  f"удаляем черновик, метим заказ {co.get('name', '?')}")
            deleted_details.append({'order': co.get('name', '?'), 'target': target, 'status': info['status']})
            if args.dry_run:
                counts['deleted'] += 1
                continue
            # 1) пометка в заказе (best-effort, идемпотентно)
            if co.get('id') and note != (co.get('description') or ''):
                try:
                    r1 = _requests.put(f"{BASE_URL}/entity/customerorder/{co['id']}",
                                       headers=MS_HEADERS, json={'description': note}, timeout=30)
                    if r1.status_code != 200:
                        print(f"    WARN пометка заказа {r1.status_code}: {r1.text[:120]}")
                except Exception as e:
                    print(f"    WARN пометка заказа: {e}")
            # 2) удаление черновика возврата
            try:
                r2 = _requests.delete(f"{BASE_URL}/entity/salesreturn/{d['id']}",
                                      headers=MS_HEADERS, timeout=30)
                if r2.status_code in (200, 204):
                    counts['deleted'] += 1
                else:
                    counts['error'] += 1
                    print(f"    ERROR удаление {r2.status_code}: {r2.text[:120]}")
                    error_details.append({'obj': f"Возврат {name}", 'msg': f"удаление {r2.status_code}"})
                time.sleep(0.15)
            except Exception as e:
                counts['error'] += 1
                print(f"    ERROR удаление: {e}")
                error_details.append({'obj': f"Возврат {name}", 'msg': f"удаление: {e}"})
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
                error_details.append({'obj': f"Возврат {name}", 'msg': f"комментарий {resp.status_code}"})
            time.sleep(0.15)
        except Exception as e:
            counts['error'] += 1
            print(f"    ERROR: {e}")
            error_details.append({'obj': f"Возврат {name}", 'msg': f"комментарий: {e}"})

    print(f"\n{'='*64}\nИтого:")
    print(f"  Обновлено комментариев:  {counts['updated']}")
    print(f"  Без изменений:           {counts['unchanged']}")
    print(f"  Удалено (ушли на склад Ozon): {counts['deleted']}")
    print(f"  Нет номера отправления:  {counts['no_posting']}")
    print(f"  Нет в Ozon API:          {counts['no_ozon_match']}")
    print(f"  Ошибки:                  {counts['error']}")
    print(f"\n  Где товар (проводит всегда Лера вручную, когда коробка придёт в Подрезково):")
    print(f"    🟡 едет к нам:            {len(by_action['едет к нам'])}  {by_action['едет к нам']}")
    print(f"    🔵 получен — уточнить:    {len(by_action['получен — уточнить'])}  {by_action['получен — уточнить']}")
    print(f"    ⚪ у Ozon (ждать):        {len(by_action['у Ozon'])}")
    print(f"    🔴 не придёт (удалить):   {len(by_action['не придёт'])}  {by_action['не придёт']}")
    print('='*64)

    if args.results_out:
        try:
            _export_results(counts, by_action, deleted_details, error_details, args.results_out)
        except Exception as e:
            print(f"Ошибка сохранения результатов JSON: {e}")


if __name__ == '__main__':
    main()
