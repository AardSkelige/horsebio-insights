#!/usr/bin/env python3
"""
Нет ли возвратов без себестоимости.

Проведённый возврат возвращает товар на склад по цене из поля cost. Если там ноль,
FIFO-себестоимость готовой продукции занижается — и дальше врут все отчёты о прибыли.

Ноль берётся не на пустом месте: когда возврат создан без привязки к отгрузке
(поле demand пустое), МойСкладу неоткуда узнать себестоимость, и он ставит 0.
У возвратов С привязкой поле cost вообще отсутствует — МойСклад считает сам, и
проверять их бессмысленно, будет ложное срабатывание.

Наши роботы всегда проставляют demand, поэтому находки тут — это ручные документы
и сборные возвраты с ФБО, которые Лера заводит без основания.

Убрать из отчёта: написать [ok] в описании возврата или добавить его id в
data/zero_cost_acknowledged.json.

Раньше жило внутри Health Check. Переехало сюда, чтобы вся тема возвратов была
в одном месте.

Запуск:
  python3 05_zero_cost_returns.py
  python3 05_zero_cost_returns.py --results-out results.json
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import MOYSKLAD_TOKEN, BASE_URL  # noqa: E402
# Запросы к МойСклад идут через общий слой: ожидание лимита, 429, повторы.
from msapi import http as ms_http  # noqa: E402

MS_HEADERS = {
    'Authorization': f'Bearer {MOYSKLAD_TOKEN}',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/json',
}

MONTHS_BACK = 3
ACK_FILE = Path(__file__).parent.parent / 'data' / 'zero_cost_acknowledged.json'
MS_DOC_URL = 'https://online.moysklad.ru/app/#salesreturn/edit?id='


def load_ack() -> set:
    """id возвратов, которые человек посмотрел и признал нормальными."""
    if not ACK_FILE.exists():
        return set()
    try:
        data = json.loads(ACK_FILE.read_text(encoding='utf-8'))
        return set(data if isinstance(data, list) else data.get('ids', []))
    except Exception as e:
        print(f"  Не смог прочитать {ACK_FILE.name}: {e}")
        return set()


def fetch_posted() -> list:
    """Проведённые возвраты за период."""
    date_from = (datetime.now() - timedelta(days=MONTHS_BACK * 30)).strftime('%Y-%m-%d %H:%M:%S')
    docs, offset = [], 0
    while True:
        r = ms_http.get(f'{BASE_URL}/entity/salesreturn', headers=MS_HEADERS, params={
            'filter': f'moment>={date_from};applicable=true',
            'order': 'moment,desc', 'expand': 'agent',
            'limit': 100, 'offset': offset,
        }, timeout=90)
        r.raise_for_status()
        rows = r.json().get('rows', [])
        docs.extend(rows)
        if len(rows) < 100:
            break
        offset += 100
    return docs


def zero_cost_positions(doc_id: str) -> tuple:
    """Позиции с нулевой себестоимостью и общее число позиций."""
    r = ms_http.get(f'{BASE_URL}/entity/salesreturn/{doc_id}/positions', headers=MS_HEADERS,
                      params={'limit': 100, 'expand': 'assortment'}, timeout=60)
    r.raise_for_status()
    rows = r.json().get('rows', [])
    zero = [{'name': (p.get('assortment') or {}).get('name', '?'),
             'qty': p.get('quantity', 0),
             'sale_price': (p.get('price') or 0) / 100}
            for p in rows if (p.get('cost') or 0) == 0]
    return zero, len(rows)


def build_payload(found: list, checked: int) -> dict:
    money = lambda v: f"{v:,.0f} ₽".replace(',', ' ')
    stats = [
        {"label": "С нулевой себестоимостью", "value": len(found),
         "tone": "critical" if found else "ok", **({"cat": "zero_cost"} if found else {})},
        {"label": "Проверено возвратов", "value": checked, "tone": "neutral"},
    ]
    category = {
        "key": "zero_cost", "title": "Проведены с нулевой себестоимостью — занижают FIFO",
        "severity": "critical", "kind": None, "ms_type": None, "count": len(found),
        "note": "Товар вернулся на склад по нулевой цене — из-за этого FIFO-себестоимость "
                "готовой продукции занижена, и отчёты о прибыли врут. Поправить: проставить "
                "себестоимость в позициях документа. Если так и задумано — написать [ok] "
                "в описании возврата, робот перестанет о нём напоминать.",
        "items": [
            {'key': '', 'ms_id': f['doc_id'],
             'ms_href': MS_DOC_URL + f['doc_id'],
             'object': f"Возврат №{f['doc_name']}", 'severity': 'critical',
             'detail': f"{f['moment']} · {f['agent'] or 'без контрагента'} · "
                       f"{len(f['zero_positions'])} из {f['total_positions']} позиций по нулю · "
                       + ', '.join(p['name'][:28] for p in f['zero_positions'][:3])}
            for f in found
        ],
    } if found else None

    return {
        'generated_at': datetime.now().isoformat(timespec='seconds'), 'params': {},
        'summary': {'critical': len(found), 'important': 0, 'warnings': 0,
                    'ok': checked - len(found), 'stats': stats, 'view': 'snapshot',
                    'empty_note': f"Проверено {checked} возвратов без привязки к отгрузке — "
                                  f"у всех себестоимость проставлена, FIFO не занижается. "
                                  f"Возвраты с привязкой не проверяем: там МойСклад считает сам."},
        'categories': [category] if category else [],
    }


def main():
    ap = argparse.ArgumentParser(description="Проведённые возвраты с нулевой себестоимостью")
    ap.add_argument('--results-out', type=str, default=None,
                    help="Путь для структурированного JSON находок (для страницы /checks)")
    args = ap.parse_args()

    print(f"{'=' * 64}\nВозвраты без себестоимости: {datetime.now():%Y-%m-%d %H:%M:%S}\n{'=' * 64}")
    ack = load_ack()
    docs = fetch_posted()
    print(f"Проведённых возвратов за {MONTHS_BACK} мес: {len(docs)}")

    found, checked = [], 0
    for i, doc in enumerate(docs, 1):
        desc = doc.get('description') or ''
        if doc['id'] in ack or '[ok]' in desc.lower():
            continue
        # С привязкой к отгрузке МойСклад считает себестоимость сам — поля cost нет
        if 'demand' in doc:
            continue
        checked += 1
        print(f"  [{i}/{len(docs)}] №{doc.get('name', '?')} ...", end='\r', flush=True)
        try:
            zero, total = zero_cost_positions(doc['id'])
        except Exception as e:
            print(f"\n  Ошибка по возврату №{doc.get('name', '?')}: {e}")
            continue
        time.sleep(0.2)
        if not zero:
            continue
        found.append({
            'doc_id': doc['id'], 'doc_name': doc.get('name', '?'),
            'moment': (doc.get('moment') or '')[:10],
            'agent': (doc.get('agent') or {}).get('name', ''),
            'zero_positions': zero, 'total_positions': total,
        })
    print(' ' * 60, end='\r')

    print(f"Проверено (без привязки к отгрузке): {checked}")
    if found:
        print(f"\n  Нашлись с нулевой себестоимостью: {len(found)}")
        for f in found:
            print(f"    №{f['doc_name']:<8} {f['moment']}  {f['agent'][:24]:24} "
                  f"{len(f['zero_positions'])}/{f['total_positions']} позиций")
            for p in f['zero_positions'][:4]:
                print(f"        {p['name'][:52]:54} × {p['qty']}")
    else:
        print("\n  Возвратов с нулевой себестоимостью нет")
    print('=' * 64)

    if args.results_out:
        try:
            with open(args.results_out, 'w', encoding='utf-8') as f:
                json.dump(build_payload(found, checked), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения результатов JSON: {e}")


if __name__ == '__main__':
    main()
