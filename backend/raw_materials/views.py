import uuid

from django.db.models import Max, Prefetch, Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.exceptions import ValidationError
from raw_materials.models import Batch, Issue, IssueLine, MaterialStock, Slot, SlotStock
from raw_materials.services.issue import display_name, issue
from raw_materials.services.receipts import pull_supplies, waiting_lines
from raw_materials.services.sync import sync_from_moysklad

ARCHIVE_PREFIX = '[АРХИВ]'
MOVE_URL = 'https://online.moysklad.ru/app/#move/edit?id={}'


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
        .prefetch_related(
            Prefetch('material__batches', queryset=Batch.objects.filter(quantity__gt=0), to_attr='live_batches'),
            Prefetch('material__slot_stocks', queryset=SlotStock.objects.select_related('slot')),
        )
        .order_by('material__name')
    )
    return {
        'synced_at': MaterialStock.objects.aggregate(last=Max('synced_at'))['last'],
        'receipts_waiting': waiting_lines().values('supply').distinct().count(),
        'slots': list(Slot.objects.exclude(name__startswith=ARCHIVE_PREFIX).values_list('name', flat=True)),
        'items': [
            {
                'id': stock.material.id,
                'name': stock.material.name,
                'group': stock.material.group,
                'uom': stock.material.uom_name,
                'slot': stock.slot.name if stock.slot else None,
                'slots': [s.slot.name for s in stock.material.slot_stocks.all()],
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
    pull_supplies()
    return Response(_payload())


def _issue(record):
    return {
        'id': record.id,
        'created_at': record.created_at,
        'created_by': display_name(record.created_by),
        'description': record.description,
        'receiver': record.receiver,
        'moysklad_name': record.moysklad_name,
        'moysklad_url': MOVE_URL.format(record.moysklad_id),
        'lines': [
            {
                'id': line.id,
                'batch': line.batch_id,
                'name': line.batch.material.name,
                'uom': line.batch.material.uom_name,
                'series': line.batch.series,
                'expiry_date': line.batch.expiry_date,
                'slot': line.slot.name if line.slot else None,
                'quantity': float(line.quantity),
            }
            for line in record.lines.all()
        ],
    }


def _issues():
    return (
        Issue.objects.select_related('created_by')
        .prefetch_related(Prefetch('lines', queryset=IssueLine.objects.select_related('batch__material', 'slot').order_by('id')))
    )


@api_view(['GET', 'POST'])
def issues(request):
    if request.method == 'GET':
        return Response({'items': [_issue(record) for record in _issues()[:100]]})
    body = request.data if isinstance(request.data, dict) else {}
    try:
        key = uuid.UUID(str(body.get('key')))
    except ValueError:
        raise ValidationError('Нет ключа выдачи')
    lines = body.get('lines')
    if not isinstance(lines, list) or not all(isinstance(line, dict) for line in lines):
        raise ValidationError('Нет строк выдачи')
    record = issue(request.user, key, lines, body.get('receiver'))
    return Response(_issue(_issues().get(pk=record.pk)), status=201)
