from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from raw_materials.models import Batch, BatchMovement

TOLERANCE = Decimal('0.001')


def _trim_order(batch):
    return (not batch.series, batch.expiry_date or date.max, batch.received_at)


def move_batch(batch, delta, kind):
    batch.quantity += delta
    batch.save(update_fields=['quantity'])
    BatchMovement.objects.create(batch=batch, kind=kind, quantity=delta)


@transaction.atomic
def reconcile(stock, kind=BatchMovement.RECONCILE):
    batches = list(Batch.objects.select_for_update().filter(material=stock.material, quantity__gt=0))
    target = max(stock.quantity, Decimal(0))
    diff = target - sum((b.quantity for b in batches), Decimal(0))
    if abs(diff) < TOLERANCE:
        return Decimal(0)

    if diff > 0:
        batch = next((b for b in batches if not b.series), None)
        if batch is None:
            batch = Batch.objects.create(material=stock.material, received_at=timezone.now())
        move_batch(batch, diff, kind)
        return diff

    left = -diff
    for batch in sorted(batches, key=_trim_order):
        cut = min(left, batch.quantity)
        move_batch(batch, -cut, kind)
        left -= cut
        if left <= 0:
            break
    return diff
