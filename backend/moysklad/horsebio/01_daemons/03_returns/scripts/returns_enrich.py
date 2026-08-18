#!/usr/bin/env python3
"""
Общий движок простановки статусов на черновиках возвратов.

Логика для Озона и ВБ одна и та же: взять непроведённые возвраты нужного агента,
найти по описанию заказа ключ (номер отправления / номер задания), спросить у
маркетплейса, где физически коробка, и записать это статусом документа. Разница
только в источнике данных — её описывает модуль-источник (ozon_returns,
wb_returns) через общий набор функций:

    LABEL, AGENT_NAMES, MARK, ORDER_MARK
    fetch_map(days_back) -> {ключ: [запись, ...]}
    key_from_order(order) -> ключ | None
    state_for_group(infos, warn_days) -> имя статуса
    is_draft_dead(infos, warn_days) -> bool
    describe(infos) -> хвост описания документа
    order_note(infos) -> хвост пометки в заказе

Черновики, для которых ключ не нашёлся (возвраты ФБО, документы, заведённые
руками), движок не трогает вообще — статус на них ставят люди.
"""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

import requests as _requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '_shared'))
from api_client import MOYSKLAD_TOKEN, BASE_URL  # noqa: E402
from return_states import (ensure_states, IN_TRANSIT, AT_PICKUP, AT_OUR_SITE,  # noqa: E402
                           STUCK, GONE_TO_MP, DONE)

MS_HEADERS = {
    'Authorization': f'Bearer {MOYSKLAD_TOKEN}',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/json',
}

# Столько дней в пути — и возврат считается зависшим. Согласовано с проверкой
# «Возвраты в пути» (PENDING_RETURN_WARN_DAYS в 01_health_check.py).
WARN_DAYS = 30


def fetch_drafts(agent_names) -> list:
    """Непроведённые возвраты нужных агентов с отгрузкой, заказом и статусом."""
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
    return [d for d in docs if (d.get('agent') or {}).get('name') in agent_names]


def build_description(base_desc: str, tail: str, mark: str) -> str:
    """Идемпотентно заменить/добавить хвост со статусом маркетплейса.

    Дату начала возврата источник пишет в ISO — её читает проверка «Возвраты в
    пути»: возраст самого документа врёт, если черновик заведён задним числом.
    """
    base = base_desc.split(mark)[0].rstrip()
    return f"{base}{mark}{tail} · {datetime.now():%d.%m}"


def build_order_note(base_desc: str, tail: str, mark: str) -> str:
    """Идемпотентно добавить в описание ЗАКАЗА пометку об удалённом черновике."""
    base = base_desc.split(mark)[0].rstrip()
    return f"{base}{mark}{tail} · {datetime.now():%d.%m}"


def delete_dead_draft(doc, order, tail, order_mark, dry_run) -> str | None:
    """Пометить заказ и удалить черновик. Возвращает текст ошибки или None."""
    if dry_run:
        return None
    note = build_order_note(order.get('description') or '', tail, order_mark)
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


def run(source, dry_run: bool = False, results_out: str | None = None, days_back: int = 240):
    """Прогон для одного источника. Возвращает раскладку по статусам."""
    print(f"{'=' * 64}\nСтатусы возвратов {source.LABEL}: {datetime.now():%Y-%m-%d %H:%M:%S}")
    if dry_run:
        print("[DRY-RUN — в МС ничего не пишется]")
    print('=' * 64)

    states = ensure_states(create=not dry_run)
    omap = source.fetch_map(days_back)
    print(f"Записей у маркетплейса: {sum(len(v) for v in omap.values())} по {len(omap)} отправлениям")

    drafts = fetch_drafts(source.AGENT_NAMES)
    print(f"Черновиков {source.LABEL} в МС: {len(drafts)}\n")

    by_state = defaultdict(list)
    deleted, errors = [], []
    counts = {'updated': 0, 'unchanged': 0, 'no_key': 0, 'no_match': 0, 'done_by_hand': 0}

    for d in drafts:
        name = d.get('name', '?')
        # Человек уже закрыл вопрос руками — не спорим и не перетираем.
        if (d.get('state') or {}).get('name') == DONE:
            counts['done_by_hand'] += 1
            continue
        co = (d.get('demand') or {}).get('customerOrder') or {}
        key = source.key_from_order(co) if co else None
        if not key:
            counts['no_key'] += 1
            print(f"  SKIP {name}: нет ключа сопоставления (ФБО или заведён вручную) — не трогаем")
            continue
        infos = omap.get(key)
        if not infos:
            counts['no_match'] += 1
            # Возврат старше окна опроса. Если статус уже стоял — он верен на момент
            # последней сверки, оставляем как есть. Если статуса нет — стоит знать.
            had = (d.get('state') or {}).get('name')
            if had:
                print(f"  вне окна {name}: {key} — оставляем статус «{had}»")
            else:
                print(f"  WARN {name}: {key} нет в данных {source.LABEL} и статуса тоже нет")
            continue

        if source.is_draft_dead(infos, WARN_DAYS):
            tail = source.order_note(infos)
            print(f"  DEL  {name}:{tail} — удаляем, метим заказ {co.get('name', '?')}")
            err = delete_dead_draft(d, co, tail, source.ORDER_MARK, dry_run)
            if err:
                errors.append({'name': name, 'msg': err})
                print(f"    ERROR {err}")
            else:
                deleted.append({'name': name, 'id': d.get('id', ''),
                                'order': co.get('name', '?'), 'detail': tail.strip()})
            continue

        target_state = source.state_for_group(infos, WARN_DAYS)
        by_state[target_state].append({
            'name': name, 'id': d.get('id', ''), 'order': co.get('name', '?'),
            'sum_rub': round(d.get('sum', 0) / 100, 2), 'detail': source.describe(infos).strip(),
        })

        payload = {}
        if (d.get('state') or {}).get('name') != target_state:
            if target_state not in states:
                errors.append({'name': name, 'msg': f"статуса «{target_state}» нет в МС"})
                continue
            payload['state'] = states[target_state]
        new_desc = build_description(d.get('description') or '', source.describe(infos), source.MARK)
        if new_desc != (d.get('description') or ''):
            payload['description'] = new_desc

        if not payload:
            counts['unchanged'] += 1
            continue

        print(f"  {name} → {target_state:20} ({source.describe(infos).strip()[:56]})")
        if dry_run:
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

    _print_summary(source, counts, deleted, errors, by_state)
    if results_out:
        try:
            _export_results(source, by_state, deleted, errors, results_out)
        except Exception as e:
            print(f"Ошибка сохранения результатов JSON: {e}")
    return by_state


def _print_summary(source, counts, deleted, errors, by_state):
    print(f"\n{'=' * 64}\nИтого:")
    print(f"  Обновлено:               {counts['updated']}")
    print(f"  Без изменений:           {counts['unchanged']}")
    print(f"  Без ключа (не трогали):  {counts['no_key']}")
    print(f"  Закрыты руками:          {counts['done_by_hand']}")
    print(f"  Вне окна опроса:         {counts['no_match']}")
    print(f"  Удалено черновиков:      {len(deleted)}")
    print(f"  Ошибки:                  {len(errors)}")
    print("\n  Раскладка по статусам:")
    for st, items in sorted(by_state.items()):
        total = sum(i['sum_rub'] for i in items)
        print(f"    {st:20} {len(items):3}  {total:10,.0f} ₽")
    print('=' * 64)


def _export_results(source, by_state, deleted, errors, path):
    """Структурированный JSON для страницы /checks.

    Здесь намеренно нет перечисления документов. Задача этого робота служебная —
    проставить статусы; что с возвратами делать людям, показывает проверка
    «Что разобрать из возвратов», и дублировать её списками здесь значит плодить
    два источника правды с разными цифрами. Показываем только работу робота
    и то, с чем он не справился.
    """
    counted = {st: len(items) for st, items in by_state.items()}
    total = sum(counted.values())

    stats = [
        {"label": "Документов размечено", "value": total, "tone": "neutral"},
        {"label": "Едут к нам", "value": counted.get(IN_TRANSIT, 0), "tone": "neutral"},
        {"label": "Забрать в ПВЗ", "value": counted.get(AT_PICKUP, 0), "tone": "neutral"},
        {"label": "У нас — разобрать", "value": counted.get(AT_OUR_SITE, 0), "tone": "neutral"},
        {"label": "Завис в пути", "value": counted.get(STUCK, 0), "tone": "neutral"},
        {"label": "Ошибки", "value": len(errors), "tone": "critical" if errors else "ok",
         **({"cat": "errors"} if errors else {})},
    ]

    categories = []
    if errors:
        categories.append({
            "key": "errors", "title": "Не смог проставить статус", "severity": "critical",
            "kind": None, "ms_type": None, "count": len(errors),
            "items": [{"key": "", "ms_id": "", "object": f"Возврат {e['name']}",
                       "severity": "critical", "detail": e['msg']} for e in errors],
        })

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"), "params": {},
        "summary": {"critical": len(errors), "important": 0, "warnings": 0,
                    "ok": total, "stats": stats},
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
