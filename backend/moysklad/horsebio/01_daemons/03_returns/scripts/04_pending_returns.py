#!/usr/bin/env python3
"""
Что разобрать из возвратов: какие требуют действия и сколько в них денег.

Раньше это считалось внутри Health Check — вместе с проверками себестоимости, раз
в сутки и без своей кнопки. Возвраты давно стали отдельной темой со своим роботом
и статусами, поэтому проверка переехала сюда: своё расписание, свой запуск.

Что считаем: все непроведённые возвраты покупателей. Черновик — штатное состояние,
документ проводят, когда товар физически дошёл до склада. Вопрос в том, сколько он
так висит и что с ним делать — на это отвечает статус, который ставят роботы
маршрутов (02_enrich_ozon_returns.py, 03_enrich_wb_returns.py):

  • «Ушёл на склад МП» — товар к нам не приедет, это не деньги в дороге. Пропускаем.
  • «У нас — разобрать» и «Разложено по полкам» — коробка на складе, осталось провести.
  • «Забрать в ПВЗ» — лежит в пункте выдачи; если не съездить, срок хранения истечёт
    и товар пропадёт (так у нас сгорел 21 вывоз со склада ВБ).
  • «Завис в пути» — робот уже выяснил у маркетплейса, что возврат встал. Верим ему.
  • без статуса (ФБО, заведённые вручную) — судим по возрасту документа.

Возраст берём из описания: роботы пишут туда дату начала возврата маркером
«· с ГГГГ-ММ-ДД». Дата самого документа врёт, если черновик заведён задним числом.

Запуск:
  python3 04_pending_returns.py
  python3 04_pending_returns.py --results-out results.json
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

import requests as _requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import MOYSKLAD_TOKEN, BASE_URL  # noqa: E402
from return_states import AT_PICKUP, AT_OUR_SITE, STUCK, GONE_TO_MP, DONE  # noqa: E402

MS_HEADERS = {
    'Authorization': f'Bearer {MOYSKLAD_TOKEN}',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/json',
}

# Столько дней в пути — и возврат считается зависшим (то же значение, что у роботов маршрутов)
WARN_DAYS = 30
# Насколько глубоко смотрим непроведённые возвраты
MONTHS_BACK = 6
# Дату начала возврата роботы маршрутов пишут в описание этим маркером
SINCE_RE = re.compile(r'· с (\d{4}-\d{2}-\d{2})')

MS_DOC_URL = 'https://online.moysklad.ru/app/#salesreturn/edit?id='


def fetch_pending() -> list:
    """Непроведённые возвраты за период, с агентом и статусом."""
    date_from = (datetime.now() - timedelta(days=MONTHS_BACK * 30)).strftime('%Y-%m-%d %H:%M:%S')
    docs, offset = [], 0
    while True:
        r = _requests.get(f'{BASE_URL}/entity/salesreturn', headers=MS_HEADERS, params={
            'filter': f'moment>={date_from};applicable=false',
            'order': 'moment,asc',
            'expand': 'agent,state',
            'limit': 100, 'offset': offset,
        }, timeout=90)
        r.raise_for_status()
        rows = r.json().get('rows', [])
        docs.extend(rows)
        if len(rows) < 100:
            break
        offset += 100
    return docs


def age_of(doc: dict, now: datetime) -> int:
    """Сколько дней висит возврат — от начала возврата, а не от даты документа."""
    m = SINCE_RE.search(doc.get('description') or '')
    src = m.group(1) if m else (doc.get('moment') or '')[:10]
    try:
        return (now - datetime.strptime(src, '%Y-%m-%d')).days
    except ValueError:
        return 0


def classify(doc: dict, now: datetime) -> dict | None:
    """Разложить возврат по смыслу. None — в подсчёт не идёт."""
    state = (doc.get('state') or {}).get('name', '')
    if state == GONE_TO_MP:
        return None  # к нам не приедет — это не деньги в дороге
    age = age_of(doc, now)
    at_our_site = state in (AT_OUR_SITE, DONE)
    at_pickup = state == AT_PICKUP
    # Статус выставлен роботом по данным маркетплейса — он знает точнее возраста.
    # Возраст остаётся критерием только там, где статуса нет (ФБО, ручные).
    overdue = (state == STUCK) if state else (age >= WARN_DAYS)
    return {
        'doc_id': doc.get('id', ''),
        'doc_name': doc.get('name', '?'),
        'moment': (doc.get('moment') or '')[:10],
        'age_days': age,
        'sum_rub': round(doc.get('sum', 0) / 100, 2),
        'agent': (doc.get('agent') or {}).get('name', ''),
        'state': state,
        'at_our_site': at_our_site,
        'at_pickup': at_pickup,
        'overdue': overdue,
    }


def build_payload(items: list) -> dict:
    """JSON для страницы /checks — формат тот же, что был у Health Check."""
    money = lambda v: f"{v:,.0f} ₽".replace(',', ' ')
    pick = lambda f: [i for i in items if i[f]]
    at_pickup, at_site, overdue = pick('at_pickup'), pick('at_our_site'), pick('overdue')
    total = sum(i['sum_rub'] for i in items)
    s = lambda lst: round(sum(i['sum_rub'] for i in lst), 2)

    stats = [
        {"label": "Едут к нам", "value": len(items) - len(at_site) - len(at_pickup), "tone": "neutral"},
        {"label": "Денег в дороге", "value": money(total - s(at_site) - s(at_pickup)), "tone": "neutral"},
        {"label": "Забрать в ПВЗ", "value": len(at_pickup), "tone": "warning" if at_pickup else "neutral"},
        {"label": "Уже у нас", "value": len(at_site), "tone": "warning" if at_site else "neutral"},
        {"label": f"Застряли дольше {WARN_DAYS} дн", "value": len(overdue), "tone": "warning" if overdue else "neutral"},
    ]

    category = {
        "key": "pending_returns", "title": "Возвраты: ждут поступления товара",
        "severity": None, "kind": None, "ms_type": None, "count": len(items),
        "items": [
            {
                'key': '', 'ms_id': i['doc_id'],
                'ms_href': (MS_DOC_URL + i['doc_id']) if i['doc_id'] else '',
                'object': f"№{i['doc_name']}",
                'severity': 'warning' if (i['overdue'] or i['at_our_site'] or i['at_pickup']) else 'info',
                'sum_rub': i['sum_rub'], 'age_days': i['age_days'], 'moment': i['moment'],
                'agent': i['agent'], 'state': i['state'],
                'at_our_site': i['at_our_site'], 'at_pickup': i['at_pickup'],
                'detail': f"{i['moment']} · {i['age_days']} дн · {money(i['sum_rub'])}"
                          + (f" · {i['agent']}" if i['agent'] else '')
                          + (f" · {i['state']}" if i['state'] else ''),
            }
            for i in items
        ],
    }

    return {
        'generated_at': datetime.now().isoformat(timespec='seconds'), 'params': {},
        'summary': {
            # «Проблема» — только то, что требует действия сверх обычного разбора
            'critical': 0, 'important': len(overdue) + len(at_pickup), 'warnings': 0,
            'ok': len(at_site),
            'pending_returns': {
                'count': len(items), 'total_rub': round(total, 2),
                'overdue': len(overdue), 'overdue_rub': s(overdue),
                'at_our_site': len(at_site), 'at_our_site_rub': s(at_site),
                'at_pickup': len(at_pickup), 'at_pickup_rub': s(at_pickup),
                'warn_days': WARN_DAYS,
            },
            'stats': stats, 'view': 'snapshot',
            'empty_note': 'Незакрытых возвратов нет — всё, что вернулось, разобрано и проведено.',
        },
        'categories': [category],
    }


def main():
    ap = argparse.ArgumentParser(description="Какие возвраты требуют действия и сколько в них денег")
    ap.add_argument('--results-out', type=str, default=None,
                    help="Путь для структурированного JSON находок (для страницы /checks)")
    args = ap.parse_args()

    print(f"{'=' * 64}\nЧто разобрать из возвратов: {datetime.now():%Y-%m-%d %H:%M:%S}\n{'=' * 64}")
    now = datetime.now()
    docs = fetch_pending()
    items = [x for x in (classify(d, now) for d in docs) if x]
    skipped = len(docs) - len(items)

    total = sum(i['sum_rub'] for i in items)
    print(f"Непроведённых возвратов за {MONTHS_BACK} мес: {len(docs)}"
          + (f" (из них {skipped} ушли на склад МП — не считаем)" if skipped else ''))
    print(f"Ждут поступления: {len(items)} на {total:,.0f} ₽\n")

    for label, key in (('Забрать в ПВЗ', 'at_pickup'), ('Уже у нас — провести', 'at_our_site'),
                       (f'Застряли дольше {WARN_DAYS} дн', 'overdue')):
        group = [i for i in items if i[key]]
        if group:
            print(f"  {label}: {len(group)} на {sum(i['sum_rub'] for i in group):,.0f} ₽")
            for i in sorted(group, key=lambda x: -x['age_days'])[:10]:
                print(f"    №{i['doc_name']:<8} {i['age_days']:>4} дн  {i['sum_rub']:>9,.0f} ₽  "
                      f"{i['agent'][:22]:22} {i['state']}")
    print('=' * 64)

    if args.results_out:
        try:
            with open(args.results_out, 'w', encoding='utf-8') as f:
                json.dump(build_payload(items), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения результатов JSON: {e}")


if __name__ == '__main__':
    main()
