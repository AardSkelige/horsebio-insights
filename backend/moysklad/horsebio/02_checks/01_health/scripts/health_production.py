from datetime import datetime

STUCK_DAYS = 30
DETAIL_ROWS = 3


def _date(value):
    return datetime.strptime(value[:10], '%Y-%m-%d') if value else None


def _planned(task):
    return task.get('deliveryPlannedMoment') or task.get('moment')


def age_days(planned, now):
    return (now.date() - _date(planned).date()).days


def stuck_candidates(tasks, now, days=STUCK_DAYS):
    result = []
    for task in tasks:
        if not task.get('applicable') or not (task.get('awaiting') or task.get('reserve')):
            continue
        planned = _planned(task)
        if planned and age_days(planned, now) > days:
            result.append(task)
    return result


def undone_rows(stages, products):
    last = {}
    for stage in stages:
        row = stage['productionRow']['meta']['href']
        if row not in last or stage['orderingPosition'] > last[row]['orderingPosition']:
            last[row] = stage
    rows = []
    for row, stage in last.items():
        total = stage.get('totalQuantity') or 0
        done = stage.get('completedQuantity') or 0
        if done + (stage.get('skippedQuantity') or 0) >= total:
            continue
        names = [p['assortment'].get('name', '?') for p in products
                 if p['productionRow']['meta']['href'] == row]
        rows.append({'name': ', '.join(names) or '?', 'done': done, 'total': total})
    return rows


def rows_detail(rows, limit=DETAIL_ROWS):
    text = ', '.join(f"{r['name']}: сделано {r['done']:g} из {r['total']:g}" for r in rows[:limit])
    if len(rows) > limit:
        text += f" и ещё {len(rows) - limit}"
    return text


class ProductionChecksMixin:

    def check_stuck_production(self):
        self._section_header(f"Зависшие производственные задания (план прошёл больше {STUCK_DAYS} дн. назад)")
        now = datetime.now()
        failed = []
        for task in stuck_candidates(self.h._get_all_pages('/entity/productiontask'), now):
            try:
                stages = self.h._get_all_pages('/entity/productionstage', {
                    'filter': f"productionTask={task['meta']['href']}",
                })
                products = self.h._get_all_pages(f"/entity/productiontask/{task['id']}/products", {
                    'expand': 'assortment',
                })
            except Exception as e:
                failed.append(task.get('name', '?'))
                print(f"  ❌ №{task.get('name', '?')}: не удалось прочитать этапы ({e})")
                continue
            rows = undone_rows(stages, products)
            if not rows:
                continue
            flags = [label for key, label in (('awaiting', 'ожидание'), ('reserve', 'резерв')) if task.get(key)]
            planned = _planned(task)[:10]
            item = {
                'doc_id': task['id'],
                'doc_name': task.get('name', '?'),
                'href': task['meta'].get('uuidHref', ''),
                'planned': planned,
                'age_days': age_days(planned, now),
                'flags': flags,
                'rows': rows,
            }
            self.stats['stuck_production'].append(item)
            print(f"  ⚠️  №{item['doc_name']}  план {planned} ({item['age_days']} дн.)  висит: {', '.join(flags)}")
            for r in rows:
                print(f"      • {r['name']}: сделано {r['done']:g} из {r['total']:g}")
        if failed:
            print(f"  ❌ Не проверены задания: {', '.join(failed)}")
        if not self.stats['stuck_production'] and not failed:
            print("  ✅ Зависших заданий не найдено")
        print()
