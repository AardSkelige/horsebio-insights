from datetime import date

from core.models import RawMaterial
from protocols.models import ManualSeries
from protocols.services.assemble import group_rows, variant
from protocols.services.render import render
from raw_materials.models import Batch


class ProtocolError(Exception):
    pass


def _qty(value):
    try:
        return float(str(value or 0).replace(',', '.'))
    except ValueError:
        raise ProtocolError(f'Количество «{value}» не число')


def _date(value):
    if not value:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _remember(rows):
    for row in rows:
        material = RawMaterial.objects.filter(external_id=row.get('material_id')).first()
        if material is None or not row.get('series'):
            continue
        if Batch.objects.filter(material=material, series=row['series']).exists():
            continue
        ManualSeries.objects.update_or_create(material=material, defaults={
            'series': row['series'],
            'expiry_date': _date(row.get('expiry_date')),
            'manufacturer': row.get('manufacturer') or '',
        })


def _group(task, index):
    groups = group_rows(task)
    if not isinstance(index, int) or not 0 <= index < len(groups):
        raise ProtocolError('Протокол не найден в задании')
    return groups[index]


def build(task, index, rows):
    group = _group(task, index)
    if group['template'] is None:
        raise ProtocolError('Для этой продукции не выбран шаблон протокола')
    prepared = variant(group, date.fromisoformat(task['moment']))
    materials = [
        {
            'template_name': row['row_name'],
            'qty': _qty(row.get('qty')),
            'manufacturer': row.get('manufacturer') or '',
            'series': row.get('series') or '',
            'expiry_date': _date(row.get('expiry_date')).strftime('%d.%m.%Y') if row.get('expiry_date') else '',
        }
        for row in rows if _qty(row.get('qty')) > 0
    ]
    _remember(rows)
    content = render(group['template'], task['name'], materials, prepared['labels'], prepared['products'])
    return content, f"Протокол {task['name']} {group['template'].title}.docx"
