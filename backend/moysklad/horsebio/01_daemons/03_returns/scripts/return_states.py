#!/usr/bin/env python3
"""
Статусы черновиков возвратов покупателей в МойСкладе.

Зачем: до этого робот писал, где физически находится товар, строкой в описании
документа («· Ozon: Получен [МО_ХИМКИ_96] → ...»). В списке возвратов это
нечитаемо и не фильтруется. Статус — цветная плашка в колонке и фильтр в UI.

API возврата покупателя поддерживает поле state, но в аккаунте статусов не было
заведено ни одного — этот модуль их создаёт и отдаёт карту «имя → meta».
UUID статусов не хардкодим: ищем по имени, создаём недостающие. Скрипт можно
гонять сколько угодно раз — повторно ничего не создастся.

Имена нейтральны к маркетплейсу: те же статусы носят и возвраты ВБ.

Запуск:
  python3 return_states.py            # показать, что заведено сейчас
  python3 return_states.py --create   # создать недостающие (нужны права админа)
"""
import os
import sys
import argparse
import requests as _requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import MOYSKLAD_TOKEN, BASE_URL  # noqa: E402

MS_HEADERS = {
    'Authorization': f'Bearer {MOYSKLAD_TOKEN}',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/json',
}

STATES_URL = f'{BASE_URL}/entity/salesreturn/metadata/states'
METADATA_URL = f'{BASE_URL}/entity/salesreturn/metadata'

# Цвет в МС — ARGB одним целым; альфа-байт нулевой, то есть R*65536 + G*256 + B.
# stateType: Regular — рабочий, Unsuccessful — финальный отрицательный
# (документ проводить не будем, товар до нас не доедет).
IN_TRANSIT = 'Едет к нам'
AT_PICKUP = 'Забрать в ПВЗ'
AT_OUR_SITE = 'У нас — разобрать'
STUCK = 'Завис в пути'
GONE_TO_MP = 'Ушёл на склад МП'
# Ставится руками, роботом — никогда. Отметка «вопрос закрыт»: коробку разобрали,
# товар вернулся на место. Робот такие документы не трогает, даже если у него
# есть что сказать про маршрут.
DONE = 'Разложено по полкам'

# Каждый статус отвечает на два вопроса: что с товаром и кто с этим что делает.
STATE_DEFS = [
    # (имя,        цвет,     rgb,           тип,            кто действует — и что)
    (IN_TRANSIT,  0x78909C, 'серо-синий',  'Regular',      'никто: маркетплейс везёт, ждём'),
    (AT_PICKUP,   0xF57C00, 'оранжевый',   'Regular',      'водитель: коробка в пункте выдачи — съездить забрать'),
    (AT_OUR_SITE, 0xFFB300, 'жёлтый',      'Regular',      'Лера: товар на складе — проверить и провести'),
    (STUCK,       0xE53935, 'красный',     'Regular',      'Марат: больше месяца в пути — писать в поддержку МП'),
    (GONE_TO_MP,  0x546E7A, 'тёмно-серый', 'Unsuccessful', 'никто: к нам не приедет, документ закроется сам'),
    (DONE,        0x43A047, 'зелёный',     'Successful',   'уже никто: разобрали и разложили, вопрос закрыт'),
]


def fetch_states() -> dict:
    """Имя статуса → его объект (включая meta). Пусто, если статусов нет."""
    r = _requests.get(METADATA_URL, headers=MS_HEADERS, timeout=30)
    r.raise_for_status()
    return {s['name']: s for s in r.json().get('states', [])}


def ensure_states(create: bool = True) -> dict:
    """Карта «имя → meta» для наших статусов. Недостающие создаёт (если create)."""
    existing = fetch_states()
    for name, color, _rgb, state_type, _hint in STATE_DEFS:
        if name in existing:
            continue
        if not create:
            continue
        r = _requests.post(STATES_URL, headers=MS_HEADERS, timeout=30,
                           json={'name': name, 'color': color, 'stateType': state_type})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"не удалось создать статус «{name}»: {r.status_code} {r.text[:200]}")
        existing[name] = r.json()
        print(f"  + создан статус «{name}» ({state_type})")
    return {name: {'meta': s['meta']} for name, s in existing.items()}


def main():
    ap = argparse.ArgumentParser(description="Статусы возвратов покупателей в МС")
    ap.add_argument('--create', action='store_true', help="Создать недостающие статусы")
    args = ap.parse_args()

    before = fetch_states()
    print(f"Статусов возвратов в аккаунте: {len(before)}")
    for name in before:
        print(f"  • {name}")

    if not args.create:
        missing = [d[0] for d in STATE_DEFS if d[0] not in before]
        print(f"\nНе хватает ({len(missing)}): {', '.join(missing) or '—'}")
        print("Запусти с --create, чтобы создать.")
        return

    print("\nСоздаю недостающие:")
    ensure_states(create=True)
    after = fetch_states()
    print(f"\nИтого статусов: {len(after)}")
    for name, _c, rgb, state_type, hint in STATE_DEFS:
        mark = '✓' if name in after else '✗'
        print(f"  {mark} {name:20} {rgb:12} {state_type:12} — {hint}")


if __name__ == '__main__':
    main()
