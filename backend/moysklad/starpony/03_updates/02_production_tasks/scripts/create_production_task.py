#!/usr/bin/env python3
"""
Создать одно производственное задание под несколько заказов покупателей.
Позиции суммируются по техкартам, ПЗ привязывается ко всем заказам сразу.

Если есть незапущенное ПЗ (статус "подготовка") — новые заказы добавляются
в него автоматически. Чтобы принудительно создать отдельное ПЗ — флаг --new.

Маппинг "код товара → техкарта" строится динамически из МойСклад.

Использование:
    python3 create_production_task.py --all                  # все открытые заказы без ПЗ
    python3 create_production_task.py 00008 00009 00010      # конкретные заказы
    python3 create_production_task.py --dry-run --all        # только показать, не создавать
    python3 create_production_task.py --all --new            # всегда создавать новое ПЗ
"""

import os
import sys
import requests
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[5] / '.env')

TOKEN = os.getenv('STARPONY_MOYSKLAD_TOKEN')
if not TOKEN:
    raise ValueError("STARPONY_MOYSKLAD_TOKEN environment variable is required")
BASE = 'https://api.moysklad.ru/api/remap/1.2'
H = {
    'Authorization': f'Bearer {TOKEN}',
    'Accept-Encoding': 'gzip',
    'Content-Type': 'application/json'
}

ORG       = '057cfc80-08e4-11f1-0a80-0f1e00116f3b'
STORE_MAT = 'dc54b320-08e3-11f1-0a80-07df0010eb97'  # Производство
STORE_OUT = '8e8e6213-08e5-11f1-0a80-15a700118df4'  # Готовая продукция
STATE_PODGOTOVKA = '8c5460ff-08eb-11f1-0a80-03700012292a'  # подготовка

ALLOWED_STATES = {'Новый'}
TIMEOUT = 30
SKIP_ITEM_NAME_PREFIXES = {'Доставка'}  # Позиции без техкарты, которые не нужно производить


def href_to_id(href):
    return href.split('/')[-1].split('?')[0]


def meta(type_, id_):
    return {'meta': {
        'href': f'{BASE}/entity/{type_}/{id_}',
        'type': type_,
        'mediaType': 'application/json'
    }}


def build_plan():
    """Построить маппинг {код товара: id техкарты} из всех техкарт в МойСклад."""
    plan = {}
    offset = 0
    while True:
        r = requests.get(f'{BASE}/entity/processingplan', headers=H,
                         params={'limit': 100, 'offset': offset,
                                 'expand': 'products.assortment'}, timeout=TIMEOUT)
        rows = r.json().get('rows', [])
        for p in rows:
            for prod in p.get('products', {}).get('rows', []):
                code = prod.get('assortment', {}).get('code', '')
                if code:
                    plan[code] = p['id']
        if len(rows) < 100:
            break
        offset += 100
    return plan


def build_stock():
    """Загрузить остатки склада Производство: {product_id: qty}."""
    stock = {}
    store_href = f'{BASE}/entity/store/{STORE_MAT}'
    offset = 0
    while True:
        r = requests.get(f'{BASE}/report/stock/all', headers=H,
                         params={'filter': f'store={store_href}',
                                 'limit': 1000, 'offset': offset}, timeout=TIMEOUT)
        rows = r.json().get('rows', [])
        for row in rows:
            mid = href_to_id(row['meta']['href'])
            stock[mid] = row.get('stock', 0)
        if len(rows) < 1000:
            break
        offset += 1000
    return stock


def get_all_open_orders():
    """Вернуть все открытые заказы [{name, id, agent_name}]."""
    r = requests.get(f'{BASE}/entity/customerorder', headers=H,
                     params={'limit': 100, 'expand': 'state,agent', 'order': 'moment,asc'}, timeout=TIMEOUT)
    result = []
    for o in r.json().get('rows', []):
        if o.get('state', {}).get('name', '') in ALLOWED_STATES:
            result.append({
                'name': o['name'],
                'id': o['id'],
                'agent': o.get('agent', {}).get('name', '?')
            })
    return result


def find_order(name):
    """Найти заказ по номеру."""
    r = requests.get(f'{BASE}/entity/customerorder', headers=H,
                     params={'filter': f'name={name}', 'limit': 1, 'expand': 'agent,state'}, timeout=TIMEOUT)
    rows = r.json().get('rows', [])
    if not rows:
        raise ValueError(f'Заказ {name} не найден')
    o = rows[0]
    return {'name': o['name'], 'id': o['id'], 'agent': o.get('agent', {}).get('name', '?')}


def has_production_task(order_id):
    """Проверить есть ли уже ПЗ у заказа. Возвращает dict {id, name, state} или None."""
    r = requests.get(f'{BASE}/entity/customerorder/{order_id}', headers=H, timeout=TIMEOUT)
    tasks = r.json().get('productionTasks', [])
    if not tasks:
        return None
    rt = requests.get(tasks[0]['meta']['href'], headers=H,
                      params={'expand': 'state,customerOrders'}, timeout=TIMEOUT)
    d = rt.json()
    return {
        'id': d['id'],
        'name': d.get('name', '?'),
        'state': d.get('state', {}).get('name', '—'),
        'description': d.get('description', ''),
        'customer_orders': d.get('customerOrders', []),
    }


def get_positions(order_id):
    """Получить позиции заказа: [(code, name, qty)]."""
    r = requests.get(f'{BASE}/entity/customerorder/{order_id}/positions',
                     headers=H, params={'expand': 'assortment', 'limit': 100}, timeout=TIMEOUT)
    return [
        (p['assortment'].get('code', ''), p['assortment'].get('name', ''), int(p['quantity']))
        for p in r.json().get('rows', [])
    ]


def get_existing_task_rows(task_id):
    """Вернуть текущие строки ПЗ: {plan_id: {row_id, volume}}."""
    r = requests.get(f'{BASE}/entity/productiontask/{task_id}/productionrows',
                     headers=H, params={'expand': 'processingPlan', 'limit': 100}, timeout=TIMEOUT)
    result = {}
    for row in r.json().get('rows', []):
        plan_id = row['processingPlan']['id']
        result[plan_id] = {
            'row_id': row['id'],
            'volume': row['productionVolume'],
        }
    return result


def get_task_materials(task_id):
    """Вернуть {material_id: {code, name, qty}} для одного ПЗ."""
    materials = defaultdict(lambda: {'code': '', 'name': '', 'qty': 0.0})
    rows_r = requests.get(f'{BASE}/entity/productiontask/{task_id}/productionrows',
                          headers=H, params={'expand': 'processingPlan', 'limit': 100}, timeout=TIMEOUT)
    for row in rows_r.json().get('rows', []):
        plan_id = row['processingPlan']['id']
        volume = row['productionVolume']
        mats_r = requests.get(f'{BASE}/entity/processingplan/{plan_id}/materials',
                               headers=H, params={'expand': 'assortment', 'limit': 100}, timeout=TIMEOUT)
        for mat in mats_r.json().get('rows', []):
            a = mat.get('assortment', {})
            mid = a.get('id', '')
            materials[mid]['code'] = a.get('code', '')
            materials[mid]['name'] = a.get('name', '?')
            materials[mid]['qty'] += mat['quantity'] * volume
    return materials


def validate_task_vs_orders(task_id, task_name, orders, plan):
    """Сверить что все позиции заказов попали в задание с правильными количествами.

    Возвращает True если всё совпадает, False если есть расхождения.
    Расхождения — это сигнал к sys.exit(1) чтобы фронт показал красный статус.
    """
    print('\n' + '─' * 70)
    print(f'🔍 Валидация ПЗ {task_name} vs заказы {", ".join("№" + o["name"] for o in orders)}')
    print('─' * 70)

    # Что ДОЛЖНО быть в задании по заказам
    expected_volumes, skipped = _compute_new_volumes(orders, plan)

    # Что реально в задании
    existing_rows = get_existing_task_rows(task_id)
    actual_volumes = {pid: r['volume'] for pid, r in existing_rows.items()}

    ok = True

    # Товары без техкарты — самая опасная ситуация (как с Cherry Granata)
    if skipped:
        print(f'\n❌ Нет техкарты — эти позиции НЕ попали в задание:')
        for s in skipped:
            print(f'   • {s}')
        ok = False

    # Расхождения в количествах
    mismatches = []
    for plan_id in set(expected_volumes) | set(actual_volumes):
        exp = expected_volumes.get(plan_id, 0)
        act = actual_volumes.get(plan_id, 0)
        if abs(exp - act) > 0.001:
            mismatches.append((plan_id, exp, act))

    if mismatches:
        print(f'\n❌ Расхождения в количествах:')
        for plan_id, exp, act in sorted(mismatches, key=lambda x: x[0]):
            diff = act - exp
            print(f'   техкарта {plan_id[:8]}…  ожидалось {exp:.0f}, в ПЗ {act:.0f}  ({diff:+.0f})')
        ok = False

    if ok:
        print('✅ Все позиции заказов совпадают с заданием\n')
    else:
        print('\n⚠️  Исправьте задание вручную перед запуском производства!\n')

    return ok


CLOSED_STATES = {'Доставлен', 'Отгружен', 'Отменен', 'Возврат'}


def audit_all_tasks(plan):
    """Проверить все заказы с ПЗ: суммарный объём по всем ПЗ заказа >= потребности заказа.

    Аудит со стороны заказа — суммируем объёмы ВСЕХ привязанных ПЗ (даже если их
    несколько или они комбинированные) и сравниваем с позициями заказа.

    Активные заказы — требуют действий при нехватке.
    Закрытые — историческая справка.
    Завершается sys.exit(1) если есть нехватка в активных заказах.
    """
    print('\n' + '═' * 70)
    print('🔎 Аудит: сверка заказов с производственными заданиями')
    print('═' * 70)

    r = requests.get(f'{BASE}/entity/customerorder', headers=H,
                     params={'limit': 100, 'expand': 'state,agent', 'order': 'moment,asc'}, timeout=TIMEOUT)
    all_orders = r.json().get('rows', [])

    active_issues = []
    closed_issues = []

    for o in all_orders:
        r2 = requests.get(f'{BASE}/entity/customerorder/{o["id"]}', headers=H, timeout=TIMEOUT)
        tasks = r2.json().get('productionTasks', [])
        if not tasks:
            continue

        order_info = {
            'id': o['id'],
            'name': o['name'],
            'agent': o.get('agent', {}).get('name', '?'),
            'state': o.get('state', {}).get('name', '—'),
        }

        # Суммируем объёмы по ВСЕМ ПЗ этого заказа
        total_pz = defaultdict(float)  # plan_id → суммарный объём
        for t in tasks:
            tid = href_to_id(t['meta']['href'])
            rt = requests.get(f'{BASE}/entity/productiontask/{tid}/productionrows',
                              headers=H, params={'expand': 'processingPlan', 'limit': 100}, timeout=TIMEOUT)
            for row in rt.json().get('rows', []):
                pid = row['processingPlan']['id']
                total_pz[pid] += row['productionVolume']

        # Ожидаемые объёмы из позиций заказа
        rp = requests.get(f'{BASE}/entity/customerorder/{o["id"]}/positions',
                          headers=H, params={'expand': 'assortment', 'limit': 100}, timeout=TIMEOUT)
        expected = {}
        skipped = []
        for p in rp.json().get('rows', []):
            code = p['assortment'].get('code', '')
            name = p['assortment'].get('name', '')
            qty = p['quantity']
            if any(name.startswith(pref) for pref in SKIP_ITEM_NAME_PREFIXES):
                continue
            if not code or code not in plan:
                skipped.append(name)
            else:
                pid = plan[code]
                expected[pid] = expected.get(pid, 0) + qty

        # Ищем нехватку: где суммарный объём ПЗ меньше потребности
        shortages = []
        for pid, exp in expected.items():
            act = total_pz.get(pid, 0)
            if act < exp - 0.001:
                shortages.append((pid, exp, act))

        if shortages or skipped:
            issue = {
                'order': order_info,
                'shortages': shortages,
                'skipped': skipped,
            }
            if order_info['state'] in CLOSED_STATES:
                closed_issues.append(issue)
            else:
                active_issues.append(issue)

    def _print_issue(issue):
        o = issue['order']
        print(f'\n  Заказ №{o["name"]} ({o["agent"]}) — статус: {o["state"]}')
        if issue['skipped']:
            print(f'    ❌ Нет техкарты (не вошли в ПЗ): {", ".join(issue["skipped"])}')
        for pid, exp, act in issue['shortages']:
            diff = act - exp
            print(f'    ❌ техкарта {pid[:8]}…  нужно {exp:.0f}, в ПЗ суммарно {act:.0f}  ({diff:+.0f})')

    has_issues = bool(active_issues or closed_issues)

    if active_issues:
        print(f'\n⚠️  АКТИВНЫЕ ЗАКАЗЫ С НЕХВАТКОЙ ({len(active_issues)}) — требуют исправления:')
        for issue in active_issues:
            _print_issue(issue)

    if closed_issues:
        print(f'\n📋 Закрытые заказы с расхождениями ({len(closed_issues)}) — историческая справка:')
        for issue in closed_issues:
            _print_issue(issue)

    if not has_issues:
        print('\n✅ Все заказы покрыты производственными заданиями\n')
    else:
        print()

    if active_issues:
        sys.exit(1)


def check_stock(task_name, task_id):
    """Проверить остатки для созданного ПЗ."""
    print('\n' + '─' * 70)
    print('📦 Проверка сырья на складе Производство')
    print('─' * 70)

    stock = build_stock()
    mats = get_task_materials(task_id)

    shortages = {mid: info for mid, info in mats.items()
                 if stock.get(mid, 0) < info['qty']}

    if not shortages:
        print('✅ Сырья хватает на всё задание\n')
        return

    print(f'❌ Не хватает {len(shortages)} позиций:\n')
    for mid, info in sorted(shortages.items(), key=lambda x: x[1]['code']):
        in_stock = stock.get(mid, 0)
        deficit = info['qty'] - in_stock
        print(f"  {info['code']}  {info['name']}")
        print(f"    Нужно: {info['qty']:.0f}  |  Есть: {in_stock:.0f}  |  ❌ не хватает: {deficit:.0f} шт")
        print()


def _compute_new_volumes(orders, plan):
    """Посчитать {plan_id: qty} и список пропущенных позиций для списка заказов."""
    plan_volumes = defaultdict(float)
    skipped = []
    for o in orders:
        positions = get_positions(o['id'])
        for code, name, qty in positions:
            if any(name.startswith(p) for p in SKIP_ITEM_NAME_PREFIXES):
                continue
            if code not in plan:
                skipped.append(f'{code} ({name})')
            else:
                plan_volumes[plan[code]] += qty
    return dict(plan_volumes), sorted(set(skipped))


def update_existing_task(task, new_orders, plan, dry_run=False):
    """Добавить новые заказы в существующее ПЗ (статус подготовка)."""
    task_id = task['id']
    task_name = task['name']

    print(f'\n🔄 Обновление ПЗ {task_name}')
    print(f'   Добавляем заказы: {", ".join("№" + o["name"] for o in new_orders)}')

    new_volumes, skipped = _compute_new_volumes(new_orders, plan)

    if not new_volumes:
        print('⚠️  Нет позиций с известными техкартами, ПЗ не обновлено')
        return

    existing_rows = get_existing_task_rows(task_id)

    if dry_run:
        print('\n🔍 [dry-run] Изменения в строках ПЗ:')
        for plan_id, add_qty in new_volumes.items():
            if plan_id in existing_rows:
                old_vol = existing_rows[plan_id]['volume']
                print(f'  техкарта {plan_id[:8]}…  {old_vol:.0f} + {add_qty:.0f} = {old_vol + add_qty:.0f} шт')
            else:
                print(f'  техкарта {plan_id[:8]}…  + {add_qty:.0f} шт (новая строка)')
        if skipped:
            print(f'⚠️  Пропущено (нет техкарты): {", ".join(skipped)}')
        return

    # Обновляем объёмы существующих строк и добавляем новые
    new_rows_to_post = []
    for plan_id, add_qty in new_volumes.items():
        if plan_id in existing_rows:
            row_id = existing_rows[plan_id]['row_id']
            new_vol = existing_rows[plan_id]['volume'] + add_qty
            r = requests.put(
                f'{BASE}/entity/productiontask/{task_id}/productionrows/{row_id}',
                headers=H,
                json={'productionVolume': new_vol},
                timeout=TIMEOUT
            )
            if not r.ok:
                print(f'❌ Ошибка обновления строки {row_id}: {r.text[:200]}')
                return
        else:
            new_rows_to_post.append({
                'processingPlan': meta('processingplan', plan_id),
                'productionVolume': add_qty,
            })

    if new_rows_to_post:
        r = requests.post(
            f'{BASE}/entity/productiontask/{task_id}/productionrows',
            headers=H,
            json=new_rows_to_post,
            timeout=TIMEOUT
        )
        if not r.ok:
            print(f'❌ Ошибка добавления новых строк: {r.text[:200]}')
            return

    # Обновляем список заказов и описание в ПЗ
    existing_order_metas = task.get('customer_orders', [])
    # customer_orders может прийти как список мета или как объект с rows
    if isinstance(existing_order_metas, dict):
        existing_order_metas = existing_order_metas.get('rows', [])
    all_order_metas = list(existing_order_metas) + [meta('customerorder', o['id']) for o in new_orders]

    # Описание: все заказы вместе
    all_order_names = []
    for om in existing_order_metas:
        href = om.get('meta', {}).get('href', '') if isinstance(om, dict) else ''
        oid = href_to_id(href) if href else ''
        all_order_names.append(oid)
    # Проще взять из описания существующего ПЗ + новые
    existing_desc = task.get('description', '')
    new_additions = ', '.join(f'№{o["name"]} {o["agent"]}' for o in new_orders)
    if existing_desc.endswith('.'):
        new_desc = existing_desc[:-1] + f', {new_additions}.'
    else:
        new_desc = existing_desc + f', {new_additions}.'

    r = requests.put(
        f'{BASE}/entity/productiontask/{task_id}',
        headers=H,
        json={
            'customerOrders': all_order_metas,
            'description': new_desc,
        },
        timeout=TIMEOUT
    )
    if not r.ok:
        print(f'❌ Ошибка обновления ПЗ: {r.text[:200]}')
        return

    print(f'✅ ПЗ {task_name} обновлено — добавлено {len(new_orders)} заказов, '
          f'{len(new_volumes)} техкарт скорректированы')

    # Все заказы привязанные к ПЗ (старые + новые)
    existing_order_ids = [
        href_to_id(om.get('meta', {}).get('href', ''))
        for om in (task.get('customer_orders') or [])
        if isinstance(om, dict)
    ]
    all_linked_orders = [{'name': oid, 'id': oid, 'agent': ''} for oid in existing_order_ids] + new_orders
    valid = validate_task_vs_orders(task_id, task_name, all_linked_orders, plan)
    check_stock(task_name, task_id)
    if not valid:
        sys.exit(1)


def create_combined_task(orders, plan, dry_run=False, force_new=False):
    """
    Создать одно ПЗ под список заказов с суммированием позиций.
    Если есть незапущенное ПЗ (подготовка) — добавит туда, если не force_new.
    orders: [{name, id, agent}]
    """
    without_task = []      # заказы без ПЗ
    podgotovka_tasks = {}  # task_id → task dict, незапущенные ПЗ

    for o in orders:
        existing = has_production_task(o['id'])
        if existing is None:
            without_task.append(o)
        elif existing['state'] == 'подготовка':
            tid = existing['id']
            if tid not in podgotovka_tasks:
                podgotovka_tasks[tid] = existing
            print(f"⏸️  Заказ №{o['name']} ({o['agent']}): ПЗ {existing['name']} в подготовке")
        else:
            print(f"⏭️  Заказ №{o['name']} ({o['agent']}): ПЗ {existing['name']} ({existing['state']}) — пропускаем")

    if not without_task:
        print('\nНет заказов без производственного задания.')
        return

    # Есть ровно одно незапущенное ПЗ — добавляем туда (если не --new)
    if podgotovka_tasks and not force_new:
        if len(podgotovka_tasks) == 1:
            task = list(podgotovka_tasks.values())[0]
            print(f'\n📌 Найдено незапущенное ПЗ {task["name"]} — добавляем в него новые заказы')
            print(f'   (чтобы создать отдельное ПЗ, запустите с флагом --new)')
            update_existing_task(task, without_task, plan, dry_run)
            return
        else:
            names = ', '.join(t['name'] for t in podgotovka_tasks.values())
            print(f'\n⚠️  Найдено несколько незапущенных ПЗ ({names}) — создаём отдельное')

    # Создаём новое ПЗ
    print(f'\n📋 Заказы для нового ПЗ: {", ".join(o["name"] for o in without_task)}')

    plan_volumes, skipped = _compute_new_volumes(without_task, plan)

    if not plan_volumes:
        print('⚠️  Нет позиций с известными техкартами, задание не создано')
        return

    order_names = ', '.join(f'№{o["name"]} {o["agent"]}' for o in without_task)
    description = f'Авто: {order_names}.'

    rows = [
        {'processingPlan': meta('processingplan', plan_id), 'productionVolume': qty}
        for plan_id, qty in plan_volumes.items()
    ]

    if dry_run:
        print(f'\n🔍 [dry-run] Создастся 1 ПЗ: {len(rows)} техкарт')
        for plan_id, qty in sorted(plan_volumes.items()):
            print(f'  техкарта {plan_id[:8]}… → {qty:.0f} шт')
        if skipped:
            print(f'⚠️  Пропущено (нет техкарты): {", ".join(skipped)}')
        return

    payload = {
        'organization': meta('organization', ORG),
        'materialsStore': meta('store', STORE_MAT),
        'productsStore': meta('store', STORE_OUT),
        'state': meta('state', STATE_PODGOTOVKA),
        'applicable': False,
        'reserve': True,
        'description': description,
        'customerOrders': [meta('customerorder', o['id']) for o in without_task],
        'productionRows': rows
    }

    r = requests.post(f'{BASE}/entity/productiontask', headers=H, json=payload, timeout=TIMEOUT)
    if r.ok:
        d = r.json()
        print(f'\n✅ ПЗ {d["name"]} создано | {len(without_task)} заказов | {len(rows)} техкарт')
        valid = validate_task_vs_orders(d['id'], d['name'], without_task, plan)
        check_stock(d['name'], d['id'])
        if not valid:
            sys.exit(1)
    else:
        print(f'❌ Ошибка: {r.text[:300]}')
        sys.exit(1)


if __name__ == '__main__':
    args = sys.argv[1:]
    dry_run   = '--dry-run' in args
    use_all   = '--all' in args
    force_new = '--new' in args
    order_names = [a for a in args if not a.startswith('--')]

    if not order_names and not use_all:
        print('Использование:')
        print('  python3 create_production_task.py --all                  # все открытые заказы без ПЗ')
        print('  python3 create_production_task.py 00008 00009            # конкретные заказы')
        print('  python3 create_production_task.py --dry-run --all        # только показать')
        print('  python3 create_production_task.py --all --new            # всегда новое ПЗ')
        sys.exit(1)

    print('⏳ Загружаю техкарты из МойСклад...')
    plan = build_plan()
    print(f'   Найдено техкарт: {len(plan)} товаров')

    if use_all:
        orders = get_all_open_orders()
        print(f'   Открытых заказов: {len(orders)} — {", ".join(o["name"] for o in orders)}\n')
    else:
        orders = [find_order(n) for n in order_names]
        print()

    create_combined_task(orders, plan, dry_run=dry_run, force_new=force_new)

    if not dry_run:
        audit_all_tasks(plan)
