"""Уведомления раздела «Склад сырья»: серии на полке, которые просрочены или скоро истекут."""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Prefetch
from django.utils import timezone

from raw_materials.models import Batch, SlotStock

from .core import CRITICAL, WARNING, Notification, provider


BIG_UNITS = {'г': 'кг', 'мл': 'л'}
SOON_DAYS = 60


def _quantity(batch):
    value, unit = batch.quantity, (batch.material.uom_name or '').lower()
    if unit in BIG_UNITS and value >= 1000:
        value, unit = value / 1000, BIG_UNITS[unit]
    number = f'{value.quantize(Decimal("0.001"), ROUND_HALF_UP).normalize():,f}'
    return f"{number.replace(',', ' ').replace('.', ',')} {unit}".strip()


def _slots(batch):
    names = [s.slot.name for s in batch.material.slot_stocks.all()]
    if not names:
        stock = getattr(batch.material, 'stock', None)
        names = [stock.slot.name] if stock and stock.slot else []
    return names


def _facts(batch):
    slots = _slots(batch)
    facts = [
        f'Серия {batch.series}' if batch.series else 'Серия не указана',
        f'годен до {batch.expiry_date:%d.%m.%Y}',
        f'на полке {_quantity(batch)}',
    ]
    if slots:
        facts.append(f"{'ячейки' if len(slots) > 1 else 'ячейка'} {', '.join(slots)}")
    return ' · '.join(facts)


@provider('raw-materials')
def expiring_batches():
    today = timezone.localdate()
    batches = (
        Batch.objects.filter(quantity__gt=0, expiry_date__lte=today + timedelta(days=SOON_DAYS))
        .select_related('material__stock__slot')
        .prefetch_related(Prefetch('material__slot_stocks', queryset=SlotStock.objects.select_related('slot')))
        .order_by('expiry_date')
    )
    for batch in batches:
        expired = batch.expiry_date < today
        yield Notification(
            key=f'raw-materials:{"expired" if expired else "expiring"}:{batch.id}',
            level=CRITICAL if expired else WARNING,
            title=f'{batch.material.name} — {"просрочено" if expired else "срок подходит к концу"}',
            body=_facts(batch),
            action=(
                'Проверьте, лежит ли серия на полке, и спишите её в МойСклад' if expired
                else 'Выдавайте эту серию в первую очередь'
            ),
            fingerprint=f'{batch.series}:{batch.expiry_date}',
        )
