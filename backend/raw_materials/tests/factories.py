from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

from core.models import RawMaterial
from raw_materials.models import Batch, MaterialStock

_counter = iter(range(1, 10_000))


def material(name='Хондроитин сульфат', uom='г'):
    return RawMaterial.objects.create(name=name, uom_name=uom, external_id=f'ms-{next(_counter)}')


def batch(material, quantity, series='', expiry=None, received=(2026, 1, 1)):
    return Batch.objects.create(
        material=material,
        series=series,
        expiry_date=date(*expiry) if expiry else None,
        quantity=Decimal(quantity),
        received_at=timezone.make_aware(datetime(*received)),
    )


def stock(material, quantity, slot=None):
    return MaterialStock.objects.create(material=material, quantity=Decimal(quantity), slot=slot)
