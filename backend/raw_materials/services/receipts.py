from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from api.exceptions import ValidationError
from api.notifications import invalidate
from core.models import RawMaterial
from raw_materials.constants import TARA_GROUP
from raw_materials.models import Batch, BatchMovement, Slot, Supply, SupplyLine
from raw_materials.services import moysklad
from raw_materials.services.reconcile import move_batch
from raw_materials.services.sync import lock_stock, material_for

RECEIPTS_SINCE = datetime(2026, 10, 21)


def _since():
    return timezone.make_aware(RECEIPTS_SINCE)


def _moment(value):
    return timezone.make_aware(datetime.strptime(value[:19], '%Y-%m-%d %H:%M:%S'))


def _tail(meta):
    return meta['href'].rsplit('/', 1)[-1].split('?')[0]


def _drop_missing(seen):
    gone = Supply.objects.filter(moment__gte=_since()).exclude(id__in=seen)
    SupplyLine.objects.filter(supply__in=gone, batch__isnull=True).delete()
    gone.filter(lines__isnull=True).delete()


def pull_supplies():
    store = moysklad.store_id()
    rows = [row for row in moysklad.supplies(store, RECEIPTS_SINCE) if row.get('applicable')]
    products = {
        _tail(p['assortment']['meta'])
        for row in rows for p in row['positions'].get('rows', [])
        if p['assortment']['meta']['type'] == 'product'
    }
    known = RawMaterial.objects.in_bulk(products, field_name='external_id')
    slots = Slot.objects.in_bulk(field_name='external_id')

    with transaction.atomic():
        lock_stock()
        seen = []
        for row in rows:
            supply, _ = Supply.objects.update_or_create(
                external_id=row['id'],
                defaults={'name': row['name'], 'moment': _moment(row['moment']), 'agent': row.get('agent', {}).get('name', '')},
            )
            seen.append(supply.id)
            lines = []
            for position in row['positions'].get('rows', []):
                if position['assortment']['meta']['type'] != 'product':
                    continue
                material = material_for(_tail(position['assortment']['meta']), known)
                if material is None:
                    continue
                slot = slots.get(_tail(position['slot']['meta'])) if position.get('slot') else None
                SupplyLine.objects.update_or_create(
                    external_id=position['id'],
                    defaults={'supply': supply, 'material': material, 'slot': slot, 'quantity': Decimal(str(position['quantity']))},
                )
                lines.append(position['id'])
            SupplyLine.objects.filter(supply=supply, batch__isnull=True).exclude(external_id__in=lines).delete()
        _drop_missing(seen)
    invalidate('raw-materials')


def _date(value):
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError:
        raise ValidationError('Укажите срок годности')


def _loose(material):
    return list(Batch.objects.select_for_update().filter(material=material, series='', quantity__gt=0).order_by('received_at'))


def loose_quantity(line_id):
    line = SupplyLine.objects.filter(pk=line_id, batch__isnull=True).first()
    if line is None:
        return None
    total = Batch.objects.filter(material_id=line.material_id, series='').aggregate(total=Sum('quantity'))['total']
    return total or Decimal(0), line.quantity


def _target(line, series, expiry, manufacturer):
    batch = Batch.objects.select_for_update().filter(material=line.material, series=series).first()
    if batch is None:
        return Batch.objects.create(
            material=line.material, series=series, expiry_date=expiry,
            manufacturer=manufacturer, quantity=0, received_at=line.supply.moment,
        )
    Batch.objects.filter(pk=batch.pk).update(expiry_date=expiry, manufacturer=manufacturer)
    return batch


def _move_sack(line, series, expiry, manufacturer):
    sources = [Batch.objects.select_for_update().get(pk=line.batch_id)] if line.batch_id else _loose(line.material)
    if not line.batch_id and not sources:
        raise ValidationError('Мешок ещё не появился на складе в МойСклад, попробуйте через минуту')

    batch = _target(line, series, expiry, manufacturer)
    left = line.quantity
    for source in sources:
        moved = min(left, source.quantity)
        if moved <= 0:
            continue
        move_batch(source, -moved, BatchMovement.RECEIPT)
        batch.refresh_from_db(fields=['quantity'])
        move_batch(batch, moved, BatchMovement.RECEIPT)
        left -= moved
    return batch


def fill_line(user, line_id, series, expiry_date, manufacturer):
    series = (series or '').strip()
    manufacturer = (manufacturer or '').strip()
    if not series:
        raise ValidationError('Впишите серию с мешка')
    expiry = _date(expiry_date)

    with transaction.atomic():
        lock_stock()
        line = SupplyLine.objects.select_for_update(of=('self',)).select_related('material', 'supply', 'batch').filter(pk=line_id).first()
        if line is None:
            raise ValidationError('Строки приёмки уже нет, обновите страницу')
        if line.material.group == TARA_GROUP:
            raise ValidationError('Таре серия не нужна')

        if line.batch and line.batch.series == series:
            Batch.objects.filter(pk=line.batch_id).update(expiry_date=expiry, manufacturer=manufacturer)
        else:
            line.batch = _move_sack(line, series, expiry, manufacturer)
        line.filled_by = user
        line.filled_at = timezone.now()
        line.save(update_fields=['batch', 'filled_by', 'filled_at'])
    invalidate('raw-materials')
    return line


def last_manufacturers(material_ids):
    known = {}
    rows = (
        Batch.objects.filter(material_id__in=material_ids).exclude(manufacturer='')
        .order_by('-received_at').values_list('material_id', 'manufacturer')
    )
    for material_id, manufacturer in rows:
        known.setdefault(material_id, manufacturer)
    return known


def waiting_lines():
    return SupplyLine.objects.filter(supply__moment__gte=_since(), batch__isnull=True).exclude(material__group=TARA_GROUP)
