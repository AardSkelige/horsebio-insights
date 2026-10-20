import sqlite3
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.models import RawMaterial
from raw_materials.models import Batch, BatchMovement, MaterialStock, Slot

ALIASES = {
    'соевый лицетин': 'соевый лецитин',
    'витамин е сухой': 'витамин е 50% сухой',
    'рыбный коллаген': 'гидролизованный коллаген рыбный',
}
NO_SERIES = {'', 'б/с', 'бс', 'без серии'}
UNITS = {'кг': ('г', 1000), 'г': ('г', 1), 'мг': ('г', Decimal('0.001')), 'л': ('мл', 1000), 'мл': ('мл', 1), 'шт': ('шт', 1)}
LATIN_TO_CYRILLIC = str.maketrans('aceopxyABCEHKMOPTX', 'асеорхуАВСЕНКМОРТХ')

BATCHES_SQL = '''
    SELECT items.name, items.unit AS item_unit, items.manufacturer, batches.unit AS batch_unit, batches.series,
           batches.remaining_qty, batches.expiry_date, batches.location, batches.created_at
    FROM batches JOIN items ON items.id = batches.item_id
    WHERE batches.status = 'active' AND batches.remaining_qty > 0
'''


class ImportBlocked(Exception):
    pass


def normalize(name):
    text = ' '.join(str(name or '').translate(LATIN_TO_CYRILLIC).lower().replace('ё', 'е').split())
    return ALIASES.get(text, text)


def convert(quantity, source_unit, target_unit):
    source = UNITS.get(normalize(source_unit))
    target = UNITS.get(normalize(target_unit))
    if not source or not target or source[0] != target[0]:
        raise ValueError(f'не перевести {source_unit} в {target_unit}')
    return (Decimal(str(quantity)) * Decimal(source[1]) / Decimal(target[1])).quantize(Decimal('0.001'))


def _slot_name(location):
    return str(location or '').split(' ')[0].upper().translate(str.maketrans('АВС', 'ABC'))


def _date(value):
    try:
        return datetime.fromisoformat(str(value or '').strip())
    except ValueError:
        return None


def _rows(db_path):
    connection = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(BATCHES_SQL).fetchall()
    finally:
        connection.close()


@transaction.atomic
def import_batches(db_path):
    if BatchMovement.objects.exclude(kind__in=[BatchMovement.IMPORT, BatchMovement.RECONCILE]).exists():
        raise ImportBlocked('по сериям уже есть рабочие движения, повторный перенос их затрёт')

    materials = {normalize(m.name): m for m in RawMaterial.objects.all()}
    slots = {s.name.upper(): s for s in Slot.objects.all()}
    Batch.objects.all().delete()
    report = {'imported': 0, 'unmatched': [], 'unconverted': []}

    for row in _rows(db_path):
        material = materials.get(normalize(row['name']))
        if material is None:
            report['unmatched'].append(row['name'])
            continue
        try:
            quantity = convert(row['remaining_qty'], row['batch_unit'] or row['item_unit'], material.uom_name)
        except ValueError as error:
            report['unconverted'].append(f"{row['name']}: {error}")
            continue

        series = str(row['series'] or '').strip()
        received = _date(row['created_at'])
        expiry = _date(row['expiry_date'])
        batch = Batch.objects.create(
            material=material,
            series='' if series.lower() in NO_SERIES else series,
            expiry_date=expiry.date() if expiry else None,
            manufacturer=str(row['manufacturer'] or '').strip(),
            quantity=quantity,
            received_at=timezone.make_aware(received) if received else timezone.now(),
        )
        BatchMovement.objects.create(batch=batch, kind=BatchMovement.IMPORT, quantity=quantity)

        stock, _ = MaterialStock.objects.get_or_create(material=material)
        if stock.slot is None and _slot_name(row['location']) in slots:
            stock.slot = slots[_slot_name(row['location'])]
            stock.save(update_fields=['slot'])
        report['imported'] += 1

    return report
