import requests
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.exceptions import APIException
from raw_materials.constants import TARA_GROUP
from raw_materials.models import Supply, SupplyLine
from raw_materials.services.receipts import RECEIPTS_SINCE, fill_line, last_manufacturers, loose_quantity, pull_supplies
from raw_materials.services.sync import sync_from_moysklad


def _line(line, suggested):
    batch = line.batch
    return {
        'id': line.id,
        'name': line.material.name,
        'uom': line.material.uom_name,
        'quantity': float(line.quantity),
        'slot': line.slot.name if line.slot else None,
        'tara': line.material.group == TARA_GROUP,
        'filled': batch is not None,
        'series': batch.series if batch else '',
        'expiry_date': batch.expiry_date if batch else None,
        'manufacturer': batch.manufacturer if batch else suggested.get(line.material_id, ''),
    }


def _supply(supply, suggested):
    lines = [_line(line, suggested) for line in supply.lines.all()]
    raw = [line for line in lines if not line['tara']]
    return {
        'id': supply.id,
        'name': supply.name,
        'moment': supply.moment,
        'agent': supply.agent,
        'lines': lines,
        'raw': len(raw),
        'waiting': sum(1 for line in raw if not line['filled']),
    }


def _payload(stale=False):
    supplies = list(
        Supply.objects.filter(moment__gte=timezone.make_aware(RECEIPTS_SINCE))
        .prefetch_related(Prefetch('lines', queryset=SupplyLine.objects.select_related('material', 'slot', 'batch')))
    )
    suggested = last_manufacturers({line.material_id for supply in supplies for line in supply.lines.all() if not line.batch_id})
    return {'stale': stale, 'items': [_supply(supply, suggested) for supply in supplies]}


@api_view(['GET'])
def receipts(request):
    try:
        pull_supplies()
    except (requests.RequestException, APIException):
        return Response(_payload(stale=True))
    return Response(_payload())


@api_view(['POST'])
def fill(request, line_id):
    body = request.data if isinstance(request.data, dict) else {}
    pending = loose_quantity(line_id)
    if pending and pending[0] < pending[1]:
        try:
            sync_from_moysklad()
        except (requests.RequestException, APIException):
            pass
    fill_line(request.user, line_id, body.get('series'), body.get('expiry_date'), body.get('manufacturer'))
    return Response(_payload())
