from django.db.models import Max, Prefetch, Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from raw_materials.models import Batch, MaterialStock
from raw_materials.services.sync import sync_from_moysklad


def _batch(batch):
    return {
        'id': batch.id,
        'series': batch.series,
        'expiry_date': batch.expiry_date,
        'manufacturer': batch.manufacturer,
        'quantity': float(batch.quantity),
    }


def _payload():
    stocks = (
        MaterialStock.objects
        .filter(Q(quantity__gt=0) | Q(material__batches__quantity__gt=0))
        .distinct()
        .select_related('material', 'slot')
        .prefetch_related(Prefetch('material__batches', queryset=Batch.objects.filter(quantity__gt=0), to_attr='live_batches'))
        .order_by('material__name')
    )
    return {
        'synced_at': MaterialStock.objects.aggregate(last=Max('synced_at'))['last'],
        'items': [
            {
                'id': stock.material.id,
                'name': stock.material.name,
                'group': stock.material.group,
                'uom': stock.material.uom_name,
                'slot': stock.slot.name if stock.slot else None,
                'quantity': float(stock.quantity),
                'batches': [_batch(b) for b in stock.material.live_batches],
            }
            for stock in stocks
        ],
    }


@api_view(['GET'])
def stock_list(request):
    return Response(_payload())


@api_view(['POST'])
def refresh(request):
    sync_from_moysklad()
    return Response(_payload())
