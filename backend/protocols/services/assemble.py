import re
from datetime import date

from core.models import RawMaterial
from protocols.models import TemplateLink
from protocols.services import series
from protocols.services.docx.matching import attach_task_packaging_hints, extract_volume
from protocols.services.render import template_rows
from raw_materials.constants import TARA_GROUP

LABEL = re.compile(r'наклейк|этикетк', re.I)


def group_rows(task):
    plan_ids = [row['plan_id'] for row in task['rows']]
    links = {
        link.plan_external_id: link.template
        for link in TemplateLink.objects.filter(plan_external_id__in=plan_ids).select_related('template__merge_into')
    }
    groups = {}
    for row in task['rows']:
        template = links.get(row['plan_id'])
        target = (template.merge_into or template) if template else None
        key = target.id if target else f"plan:{row['plan_id']}"
        group = groups.setdefault(key, {'target': target, 'templates': set(), 'rows': []})
        if template:
            group['templates'].add(template)
        group['rows'].append(row)
    for group in groups.values():
        found = group.pop('templates')
        group['template'] = next(iter(found)) if len(found) == 1 else group['target']
    return list(groups.values())


def _materials(rows):
    totals = {}
    for row in rows:
        for m in row['materials']:
            entry = totals.setdefault(m['material_id'], {'material_id': m['material_id'], 'name': m['name'], 'qty': 0})
            entry['qty'] += m['qty']
    return totals


def _template_row(name, material, qty, on_date):
    chosen = series.default(material) if material else {'series': '', 'expiry_date': None, 'manufacturer': '', 'source': ''}
    return {
        'row_name': name,
        'material_id': material.external_id if material else None,
        'material_name': material.name if material else '',
        'uom': material.uom_name if material else '',
        'qty': qty,
        **chosen,
        'expired': series.is_expired(chosen['expiry_date'], on_date),
        'options': series.options(material) if material else [],
    }


def variant(group, on_date):
    template = group['template']
    totals = _materials(group['rows'])
    labels = [
        {'source_name': m['name'], 'qty': m['qty'], 'unit': 'шт', 'volume': extract_volume(m['name'])}
        for m in totals.values() if LABEL.search(m['name'])
    ]
    others = {mid: m for mid, m in totals.items() if not LABEL.search(m['name'])}
    enriched = attach_task_packaging_hints({
        'products': [{'source_name': p['name'], 'qty': p['qty'], 'unit': 'шт'} for r in group['rows'] for p in r['products']],
        'materials': [{'source_name': m['name'], 'qty': m['qty']} for m in others.values()],
        'labels': labels,
    })
    materials = RawMaterial.objects.in_bulk(others.keys(), field_name='external_id')

    rows, placed = [], set()
    if template:
        mapping = {tm.row_name: tm.material for tm in template.materials.select_related('material')}
        for name in template_rows(template):
            material = mapping.get(name)
            in_task = material is not None and material.external_id in others
            if in_task:
                placed.add(material.external_id)
            rows.append(_template_row(name, material, others[material.external_id]['qty'] if in_task else 0, on_date))

    return {
        'template': {'id': template.id, 'title': template.title} if template else None,
        'plan_ids': [r['plan_id'] for r in group['rows']],
        'plans': [r['plan_name'] for r in group['rows']],
        'products': enriched['products'],
        'labels': enriched['labels'],
        'rows': rows,
        'unplaced': [
            {**m, 'is_tara': getattr(materials.get(mid), 'group', None) == TARA_GROUP}
            for mid, m in others.items() if mid not in placed
        ],
    }


def prepare(task):
    on_date = date.fromisoformat(task['moment'])
    return [variant(group, on_date) for group in group_rows(task)]
