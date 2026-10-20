from msapi.client import get_json


def _id(meta_holder):
    return meta_holder['meta']['href'].rstrip('/').split('/')[-1].split('?')[0]


def recent_tasks(search='', limit=40):
    params = {'limit': limit, 'order': 'moment,desc', 'expand': 'state'}
    if search:
        params['search'] = search
    return [
        {
            'id': task['id'],
            'name': task['name'],
            'moment': task['moment'][:10],
            'state': (task.get('state') or {}).get('name', ''),
            'description': task.get('description', ''),
        }
        for task in get_json('/entity/productiontask', params).get('rows', [])
    ]


def task(task_id):
    data = get_json(f'/entity/productiontask/{task_id}', {'expand': 'productionRows'})
    products = get_json(f'/entity/productiontask/{task_id}/products', {'expand': 'assortment', 'limit': 1000}).get('rows', [])
    rows = []
    for row in data['productionRows'].get('rows', []):
        plan = get_json(row['processingPlan']['meta']['href'], {'expand': 'materials.assortment'})
        volume = row['productionVolume']
        rows.append({
            'plan_id': plan['id'],
            'plan_name': plan['name'],
            'products': [
                {'name': p['assortment']['name'], 'qty': p['planQuantity']}
                for p in products if _id(p['productionRow']) == row['id']
            ],
            'materials': [
                {'material_id': m['assortment']['id'], 'name': m['assortment']['name'], 'qty': m['quantity'] * volume}
                for m in plan['materials'].get('rows', [])
            ],
        })
    return {'id': data['id'], 'name': data['name'], 'moment': data['moment'][:10], 'rows': rows}
