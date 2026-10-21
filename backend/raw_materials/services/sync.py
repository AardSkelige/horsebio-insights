from decimal import Decimal

import requests
from django.db import connection, transaction
from django.utils import timezone

from api.notifications import invalidate
from core.models import RawMaterial
from raw_materials.models import BatchMovement, MaterialStock, Slot, SlotStock
from raw_materials.services import moysklad
from raw_materials.services.reconcile import reconcile
from sync.utils import get_group_from_pathname

LOCK_KEY = 7_340_001


def _product(assortment_id):
    try:
        return moysklad.product(assortment_id)
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            return None
        raise


def material_for(assortment_id, known):
    if assortment_id in known:
        return known[assortment_id]
    details = _product(assortment_id)
    if details is None:
        return None
    uom = details.get('uom') or {}
    material, _ = RawMaterial.objects.update_or_create(
        external_id=assortment_id,
        defaults={
            'name': details.get('name'),
            'uom_name': uom.get('name'),
            'uom_description': uom.get('description'),
            'group': get_group_from_pathname(details.get('pathName', '')),
            'article': details.get('article'),
            'code': details.get('code'),
            'description': details.get('description'),
        },
    )
    return material


def lock_stock():
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [LOCK_KEY])


def _save_slots(stock, placed, slots):
    SlotStock.objects.filter(material=stock.material).delete()
    SlotStock.objects.bulk_create(
        SlotStock(material=stock.material, slot=slots[slot], quantity=Decimal(str(quantity)))
        for slot, quantity in placed.items() if slot in slots
    )


def sync_from_moysklad(kind=BatchMovement.RECONCILE):
    started = timezone.now()
    store = moysklad.store_id()
    slot_names = moysklad.slots(store)
    totals, recalculating = moysklad.stock(store)
    by_slot = moysklad.slot_stock(store)

    with transaction.atomic():
        lock_stock()
        issued = set(
            BatchMovement.objects.filter(kind=BatchMovement.ISSUE, created_at__gte=started)
            .values_list('batch__material__external_id', flat=True)
        )
        slots = {}
        for external_id, name in slot_names.items():
            slots[external_id], _ = Slot.objects.update_or_create(external_id=external_id, defaults={'name': name})

        known = RawMaterial.objects.in_bulk(totals.keys(), field_name='external_id')
        stocks = {s.material.external_id: s for s in MaterialStock.objects.select_related('material')}
        now = timezone.now()
        seen = corrected = 0

        for external_id in (set(totals) | set(stocks)) - recalculating - issued:
            stock = stocks.get(external_id)
            if stock is None:
                material = material_for(external_id, known)
                if material is None:
                    continue
                stock = MaterialStock(material=material)
            placed = by_slot.get(external_id, {})
            main = max(placed, key=placed.get) if placed else None
            stock.quantity = Decimal(str(totals.get(external_id, 0)))
            stock.slot = slots.get(main) or stock.slot
            stock.synced_at = now
            stock.save()
            _save_slots(stock, placed, slots)
            seen += 1
            if reconcile(stock, kind):
                corrected += 1

    invalidate('raw-materials')
    return {'materials': seen, 'corrected': corrected, 'skipped': len(recalculating | issued)}
