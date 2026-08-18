#!/usr/bin/env python3
"""
Простановка статуса и комментария на черновиках возвратов Озон.

Монитор (01_monitor_returns.py) заводит черновик на каждый возврат, который едет
к нам. Этот скрипт отвечает на вопрос «где коробка сейчас»: тянет статус из Ozon
API и раскладывает черновики по статусам МС — чтобы в списке возвратов было видно
глазами, что забирать, чего ждать и что пинать в поддержке.

Раньше скрипт удалял черновики, уезжающие на склад Озона. Так мы потеряли два
документа (заказы 06405 и 06469): Озон переназначил конечную точку на наш ПВЗ уже
после удаления, а восстановить удалённое некому. Теперь вместо удаления ставим
статус «Ушёл на склад МП» — документ остаётся, и если маршрут переиграется,
статус просто вернётся обратно.

Запуск:
  python3 02_enrich_ozon_returns.py            # проставить статусы и комментарии
  python3 02_enrich_ozon_returns.py --dry-run  # показать, ничего не писать
"""
import os
import sys
import time
import argparse
from collections import defaultdict
from datetime import datetime

import requests as _requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import MOYSKLAD_TOKEN, BASE_URL  # noqa: E402  (грузит backend/.env, включая OZON_*)
import ozon_returns as ozr  # noqa: E402
from return_states import ensure_states, AT_OUR_SITE, STUCK, GONE_TO_MP  # noqa: E402

MS_HEADERS = {
    'Authorization': f'Bearer {MOYSKLAD_TOKEN}',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/json',
}

# Маркер, с которого начинается наш блок статуса в описании (для идемпотентной замены)
MARK = ' · Ozon:'
# Маркер пометки в описании ЗАКАЗА: черновик удалён, возврат осел у Озона.
# След в МС остаётся, даже когда самого документа уже нет.
ORDER_MARK = '\n↩ Возврат на склад Ozon:'

# Столько дней в пути — и возврат считается зависшим (согласовано с проверкой
# «Возвраты в пути», PENDING_RETURN_WARN_DAYS).
WARN_DAYS = 30


def fetch_ozon_drafts() -> list:
    """Непроведённые возвраты Озон с раскрытыми отгрузкой, заказом и статусом."""
    docs, offset = [], 0
    while True:
        r = _requests.get(f'{BASE_URL}/entity/salesreturn', headers=MS_HEADERS, params={
            'filter': 'applicable=false',
            'expand': 'demand.customerOrder,agent,state',
            'limit': 100, 'offset': offset,
        }, timeout=60)
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
    return ozr.posting_from_text(co.get('description'))


def build_description(base_desc: str, infos: list) -> str:
    """Идемпотентно заменить/добавить блок статуса Ozon в описании."""
    base = base_desc.split(MARK)[0].rstrip()
    head = infos[0]
    where = head['place'][:34] or '—'
    return f"{base}{MARK} {head['status']} [{where}] · {ozr.age_days(head)} дн · {datetime.now():%d.%m}"


def build_order_note(base_desc: str, info: dict) -> str:
    """Идемпотентно добавить в описание ЗАКАЗА пометку об удалённом черновике."""
    base = base_desc.split(ORDER_MARK)[0].rstrip()
    return f"{base}{ORDER_MARK} {info['target']} · {info['status']} · {datetime.now():%d.%m}"


def delete_dead_draft(doc: dict, order: dict, info: dict, dry_run: bool) -> str | None:
    """Пометить заказ и удалить черновик. Возвращает текст ошибки или None."""
    if dry_run:
        return None
    note = build_order_note(order.get('description') or '', info)
    if order.get('id') and note != (order.get('description') or ''):
        try:
            r = _requests.put(f"{BASE_URL}/entity/customerorder/{order['id']}",
                              headers=MS_HEADERS, json={'description': note}, timeout=30)
            if r.status_code != 200:
                print(f"    WARN пометка заказа {r.status_code}: {r.text[:120]}")
        except Exception as e:
            print(f"    WARN пометка заказа: {e}")
    try:
        r = _requests.delete(f"{BASE_URL}/entity/salesreturn/{doc['id']}",
                             headers=MS_HEADERS, timeout=30)
        if r.status_code not in (200, 204):
            return f"удаление {r.status_code}: {r.text[:100]}"
    except Exception as e:
        return f"удаление: {e}"
    time.sleep(0.15)
    return None


def _export_results(by_state, deleted, errors, path):
    """Структурированный JSON для страницы /checks: стат-карточки + раскрываемые списки."""
    import json as _json

    at_site = by_state.get(AT_OUR_SITE, [])
    stuck = by_state.get(STUCK, [])
    gone = by_state.get(GONE_TO_MP, [])

    stats = [
        {"label": "Можно проводить", "value": len(at_site), "tone": "warning" if at_site else "neutral",
         **({"cat": "at_site"} if at_site else {})},
        {"label": "Зависли в пути", "value": len(stuck), "tone": "warning" if stuck else "neutral",
         **({"cat": "stuck"} if stuck else {})},
        {"label": "Едут к нам", "value": len(by_state.get('Едет к нам', [])), "tone": "neutral"},
        {"label": "Ушли на склад МП", "value": len(gone), "tone": "neutral",
         **({"cat": "gone"} if gone else {})},
        {"label": "Удалено черновиков", "value": len(deleted), "tone": "ok" if deleted else "neutral",
         **({"cat": "deleted"} if deleted else {})},
        {"label": "Ошибки", "value": len(errors), "tone": "critical" if errors else "neutral",
         **({"cat": "errors"} if errors else {})},
    ]

    def cat(key, title, sev, items, detail):
        return {"key": key, "title": title, "severity": sev, "kind": None, "ms_type": None,
                "count": len(items),
                "items": [{"key": "", "ms_id": i.get('id', ''), "object": f"Возврат {i['name']}",
                           "severity": sev, "detail": detail(i)} for i in items]} if items else None

    categories = [c for c in [
        cat("errors", "Ошибки", "critical", errors, lambda i: i['msg']),
        cat("at_site", "Возврат у нас — можно проводить", "important", at_site,
            lambda i: f"{i['status']} · получен {i['received_at'] or '—'} · заказ №{i['order']}"),
        cat("stuck", f"Зависли дольше {WARN_DAYS} дн — писать в поддержку Ozon", "important", stuck,
            lambda i: f"{i['status']} · {i['place']} · {i['age']} дн в пути"),
        cat("gone", "Ушли на склад Ozon — к нам не приедут", "ok", gone,
            lambda i: f"{i['status']} · {i['target']}"),
        cat("deleted", "Удалены — осели на складе Ozon", "ok", deleted,
            lambda i: f"{i['target']} · {i['status']} · заказ №{i['order']}"),
    ] if c]

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"), "params": {},
        "summary": {"critical": len(errors), "important": len(at_site) + len(stuck),
                    "warnings": 0, "ok": len(gone) + len(deleted), "stats": stats},
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="Статусы черновиков возвратов Озон по данным Ozon API")
    ap.add_argument('--dry-run', action='store_true', help="Показать, ничего не писать в МС")
    ap.add_argument('--results-out', type=str, default=None,
                    help="Путь для структурированного JSON находок (для страницы /checks)")
    args = ap.parse_args()

    print(f"{'='*64}\nСтатусы возвратов Озон: {datetime.now():%Y-%m-%d %H:%M:%S}")
    if args.dry_run:
        print("[DRY-RUN — в МС ничего не пишется]")
    print('='*64)

    states = ensure_states(create=not args.dry_run)

    omap = defaultdict(list)
    for info in ozr.fetch_returns(days_back=240):
        omap[info['posting']].append(info)
    print(f"Отправлений с возвратами в Ozon: {len(omap)}")

    drafts = fetch_ozon_drafts()
    print(f"Черновиков Озон в МС: {len(drafts)}\n")

    by_state = defaultdict(list)
    deleted = []
    errors = []
    counts = {'updated': 0, 'unchanged': 0, 'no_posting': 0, 'no_ozon_match': 0}

    for d in drafts:
        name = d.get('name', '?')
        co = (d.get('demand') or {}).get('customerOrder') or {}
        pn = posting_from_return(d)
        if not pn:
            counts['no_posting'] += 1
            print(f"  SKIP {name}: не нашёл номер отправления (ручной/ФБО?)")
            continue
        infos = omap.get(pn)
        if not infos:
            counts['no_ozon_match'] += 1
            print(f"  WARN {name}: {pn} нет в Ozon API (старый/за окном)")
            continue

        head = infos[0]
        target_state = ozr.state_for_group(infos, WARN_DAYS)

        # Возврат осел у Озона окончательно — документ бессмыслен, убираем.
        # Статус «Ушёл на склад МП» до этого момента служил надгробием: он был
        # виден в списке те 30 дней, пока маршрут ещё мог переиграться.
        if ozr.is_draft_dead(infos, WARN_DAYS):
            print(f"  DEL  {name}: {head['status']} → {head['target']} "
                  f"({ozr.age_days(head)} дн) — удаляем, метим заказ {co.get('name', '?')}")
            err = delete_dead_draft(d, co, head, args.dry_run)
            if err:
                errors.append({'name': name, 'msg': err})
                print(f"    ERROR {err}")
            else:
                deleted.append({'name': name, 'id': d.get('id', ''), 'order': co.get('name', '?'),
                                'status': head['status'], 'target': head['target']})
            continue

        by_state[target_state].append({
            'name': name, 'id': d.get('id', ''), 'order': co.get('name', '?'),
            'status': head['status'], 'place': head['place'], 'target': head['target'],
            'age': ozr.age_days(head), 'received_at': head['received_at'],
        })

        payload = {}
        if (d.get('state') or {}).get('name') != target_state:
            if target_state not in states:
                errors.append({'name': name, 'msg': f"статуса «{target_state}» нет в МС"})
                continue
            payload['state'] = states[target_state]
        new_desc = build_description(d.get('description') or '', infos)
        if new_desc != (d.get('description') or ''):
            payload['description'] = new_desc

        if not payload:
            counts['unchanged'] += 1
            continue

        print(f"  {name} → {target_state:20} ({head['status']} @ {head['place'][:24]})")
        if args.dry_run:
            counts['updated'] += 1
            continue
        try:
            resp = _requests.put(f"{BASE_URL}/entity/salesreturn/{d['id']}",
                                 headers=MS_HEADERS, json=payload, timeout=30)
            if resp.status_code == 200:
                counts['updated'] += 1
            else:
                errors.append({'name': name, 'msg': f"запись {resp.status_code}: {resp.text[:100]}"})
                print(f"    ERROR {resp.status_code}: {resp.text[:120]}")
            time.sleep(0.15)
        except Exception as e:
            errors.append({'name': name, 'msg': str(e)})
            print(f"    ERROR: {e}")

    print(f"\n{'='*64}\nИтого:")
    print(f"  Обновлено:               {counts['updated']}")
    print(f"  Без изменений:           {counts['unchanged']}")
    print(f"  Нет номера отправления:  {counts['no_posting']}")
    print(f"  Нет в Ozon API:          {counts['no_ozon_match']}")
    print(f"  Удалено (осели у Озона): {len(deleted)}")
    print(f"  Ошибки:                  {len(errors)}")
    print(f"\n  Раскладка по статусам:")
    for st, items in sorted(by_state.items()):
        print(f"    {st:20} {len(items):3}  {[i['name'] for i in items]}")
    print('='*64)

    if args.results_out:
        try:
            _export_results(by_state, deleted, errors, args.results_out)
        except Exception as e:
            print(f"Ошибка сохранения результатов JSON: {e}")


if __name__ == '__main__':
    main()
