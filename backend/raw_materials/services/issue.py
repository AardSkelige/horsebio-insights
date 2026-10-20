from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import requests
from django.db import transaction
from django.db.models import F, Prefetch, prefetch_related_objects

from api.exceptions import ExternalServiceError, ValidationError
from api.notifications import invalidate
from raw_materials.models import Batch, BatchMovement, Issue, IssueLine, MaterialStock, SlotStock
from raw_materials.services import moysklad
from raw_materials.services.reconcile import move_batch
from raw_materials.services.sync import lock_stock

TARA_GROUP = 'Тара'
STEP = Decimal('0.001')


def display_name(user):
    return user.get_full_name() or user.username


def describe(user, materials, receiver):
    kinds = {material.group == TARA_GROUP for material in materials}
    what = 'сырья и тары' if len(kinds) == 2 else 'тары' if True in kinds else 'сырья'
    return f'{display_name(user)}, выдача {what}. Получил: {receiver}'


def _quantity(value):
    quantity = Decimal(str(value))
    if not quantity.is_finite():
        raise InvalidOperation
    return quantity.quantize(STEP, ROUND_HALF_UP)


def _requested(lines):
    requested = defaultdict(Decimal)
    wanted_slots = {}
    for line in lines:
        try:
            quantity = _quantity(line['quantity'])
            batch_id = int(line['batch'])
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ValidationError('Не понял строку выдачи')
        if quantity <= 0:
            raise ValidationError('Количество должно быть больше нуля')
        requested[batch_id] += quantity
        wanted_slots.setdefault(batch_id, line.get('slot'))
    if not requested:
        raise ValidationError('Нечего выдавать')
    return requested, wanted_slots


def _checked_batches(requested):
    batches = (
        Batch.objects.select_for_update(of=('self',))
        .select_related('material__stock__slot')
        .filter(id__in=requested)
    )
    found = {batch.id: batch for batch in batches}
    if len(found) != len(requested):
        raise ValidationError('Серия уже закончилась, обновите страницу')
    for batch_id, quantity in requested.items():
        batch = found[batch_id]
        if getattr(batch.material, 'stock', None) is None:
            raise ValidationError(f'{batch.material.name}: нет остатка в МойСклад, обновите склад')
        if quantity > batch.quantity:
            raise ValidationError(
                f'{batch.material.name}, {batch.series or "без серии"}: на остатке {batch.quantity.normalize():f}'
            )
    return found


def _source_slot(batch, wanted):
    return next((s for s in batch.material.slot_stocks.all() if s.slot.name == wanted), None)


def _split(material, need, first_slot):
    if not material.slot_stocks.all():
        home = material.stock.slot
        yield (home.external_id if home else None), need
        return
    placed = sorted(
        material.slot_stocks.all(),
        key=lambda s: (s.slot_id != first_slot, s.slot_id != material.stock.slot_id, -s.quantity),
    )
    for slot_stock in placed:
        if need <= 0:
            break
        part = min(need, slot_stock.quantity)
        yield slot_stock.slot.external_id, part
        need -= part
    if need > 0:
        yield None, need


def _positions(batches, requested, slots):
    by_material = defaultdict(Decimal)
    first_slot = {}
    for batch_id, quantity in requested.items():
        material = batches[batch_id].material
        by_material[material] += quantity
        first_slot.setdefault(material, slots[batch_id].id if slots[batch_id] else None)
    return [
        (material.external_id, slot, part)
        for material, need in by_material.items()
        for slot, part in _split(material, need, first_slot[material])
    ]


def _moysklad_error(error):
    try:
        return error.response.json()['errors'][0]['error']
    except (AttributeError, ValueError, KeyError, IndexError, TypeError):
        return str(error)


def _record(user, key, description, receiver, move, batches, requested, slots, positions):
    record = Issue.objects.create(
        key=key, created_by=user, description=description, receiver=receiver,
        moysklad_id=move['id'], moysklad_name=move['name'],
    )
    taken = defaultdict(Decimal)
    for batch_id, quantity in requested.items():
        batch = batches[batch_id]
        IssueLine.objects.create(issue=record, batch=batch, slot=slots[batch_id], quantity=quantity)
        move_batch(batch, -quantity, BatchMovement.ISSUE)
        taken[batch.material_id] += quantity
    for material_id, quantity in taken.items():
        MaterialStock.objects.filter(material_id=material_id).update(quantity=F('quantity') - quantity)
    for product, slot, part in positions:
        if slot:
            placed = SlotStock.objects.filter(material__external_id=product, slot__external_id=slot)
            placed.update(quantity=F('quantity') - part)
            placed.filter(quantity__lte=0).delete()
    return record


def issue(user, key, lines, receiver):
    receiver = (receiver or '').strip()
    if not receiver:
        raise ValidationError('Укажите, кто получил')
    if len(receiver) > 100:
        raise ValidationError('Слишком длинное имя получателя')
    requested, wanted_slots = _requested(lines)
    with transaction.atomic():
        lock_stock()
        done = Issue.objects.filter(key=key).first()
        if done:
            return done

        batches = _checked_batches(requested)
        prefetch_related_objects(
            list({batch.material for batch in batches.values()}),
            Prefetch('slot_stocks', queryset=SlotStock.objects.select_related('slot')),
        )
        slots = {
            batch_id: (_source_slot(batch, wanted_slots[batch_id]) or batch.material.stock).slot
            for batch_id, batch in batches.items()
        }
        description = describe(user, {batch.material for batch in batches.values()}, receiver)
        positions = _positions(batches, requested, slots)
        try:
            move = moysklad.create_move(str(key), description, positions)
        except requests.HTTPError as error:
            raise ExternalServiceError(f'МойСклад не принял перемещение: {_moysklad_error(error)}')
        except requests.RequestException:
            raise ExternalServiceError('МойСклад не отвечает, выдача не записана')

        try:
            with transaction.atomic():
                record = _record(user, key, description, receiver, move, batches, requested, slots, positions)
        except Exception:
            moysklad.discard_move(move['id'])
            raise
    invalidate('raw-materials')
    return record
