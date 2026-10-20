from datetime import date

from raw_materials.models import Batch, BatchMovement


def _from_batch(batch, source):
    return {
        'series': batch.series,
        'expiry_date': batch.expiry_date,
        'manufacturer': batch.manufacturer,
        'source': source,
    }


def options(material):
    return [_from_batch(b, 'stock') for b in Batch.objects.filter(material=material, quantity__gt=0).exclude(series='')]


def default(material):
    issued = (
        BatchMovement.objects.filter(batch__material=material, kind__in=[BatchMovement.ISSUE, BatchMovement.RECONCILE], quantity__lt=0)
        .exclude(batch__series='').select_related('batch').order_by('-created_at').first()
    )
    if issued:
        return _from_batch(issued.batch, 'issued')
    on_stock = options(material)
    if on_stock:
        return on_stock[0]
    manual = getattr(material, 'manual_series', None)
    if manual:
        return {
            'series': manual.series,
            'expiry_date': manual.expiry_date,
            'manufacturer': manual.manufacturer,
            'source': 'manual',
        }
    return {'series': '', 'expiry_date': None, 'manufacturer': '', 'source': ''}


def is_expired(expiry_date, on_date=None):
    return bool(expiry_date) and expiry_date < (on_date or date.today())
