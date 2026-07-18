# api/services/supply_service.py

import pytz
from datetime import datetime, timedelta
from django.db.models import (
    Q, F, Sum, Count, Avg, Min, Max, ExpressionWrapper,
    Case, When, DecimalField, Value, OuterRef, Subquery, Prefetch,
)
from django.db.models.functions import TruncMonth, Coalesce
from django.core.paginator import Paginator

from core.models import Supply, SupplyItem, RawMaterial, Counterparty
from api.exceptions import NotFoundError
from api.utils import apply_date_filter

VALID_GROUPS = [
    'Тара',
    'Материалы для производства',
    'Этикетки',
]


def get_supply_analytics():
    filtered_items_prefetch = Prefetch(
        'items',
        queryset=SupplyItem.objects.filter(
            raw_material__group__in=VALID_GROUPS
        ).select_related('raw_material'),
        to_attr='filtered_items',
    )

    supplies = (
        Supply.objects
        .select_related('counterparty')
        .prefetch_related(filtered_items_prefetch)
        .filter(items__raw_material__group__in=VALID_GROUPS)
        .distinct()
    )

    result = []
    for supply in supplies:
        supply_items = supply.filtered_items
        result.append({
            'supplier_name': supply.counterparty.name,
            'supplier_id': supply.counterparty.id,
            'supply_id': supply.id,
            'supply_number': supply.number,
            'supply_date': supply.date.isoformat(),
            'total_sum': float(supply.sum),
            'items_count': len(supply_items),
            'total_quantity': float(sum(item.quantity for item in supply_items)),
            'items': [
                {
                    'material_name': item.raw_material.name,
                    'raw_material': {
                        'id': item.raw_material.id,
                        'name': item.raw_material.name,
                        'code': item.raw_material.code,
                        'group': item.raw_material.group,
                        'uom_name': item.raw_material.uom_name,
                    },
                    'quantity': float(item.quantity),
                    'price': float(item.price),
                    'total': float(item.total),
                    'uom': item.raw_material.uom_name,
                }
                for item in supply_items
            ],
        })
    return result


def get_supply_materials(start_date=None, end_date=None, search='', group=''):
    query = (
        SupplyItem.objects
        .select_related('raw_material', 'supply', 'supply__counterparty')
        .values(
            'raw_material__name',
            'raw_material__group',
            'raw_material__uom_name',
            'raw_material__code',
            'raw_material__id',
        )
        .filter(raw_material__group__in=VALID_GROUPS)
    )

    query = apply_date_filter(query, start_date, end_date, 'supply__date')

    if search:
        query = query.filter(
            Q(raw_material__name__icontains=search) |
            Q(raw_material__code__icontains=search)
        )
    if group:
        query = query.filter(raw_material__group=group)

    materials_data = query.annotate(
        total_quantity=Sum('quantity'),
        total_sum=Sum('total'),
        avg_price=Avg('price'),
        supplies_count=Count('supply', distinct=True),
        suppliers_count=Count('supply__counterparty', distinct=True),
    ).order_by('-total_quantity')

    result = []
    for material in materials_data:
        supplies_detail = (
            SupplyItem.objects
            .filter(raw_material__id=material['raw_material__id'])
            .select_related('supply', 'supply__counterparty')
            .values(
                'supply__number', 'supply__date', 'quantity', 'price', 'total',
                'supply__counterparty__name',
            )
            .order_by('-supply__date')
        )

        supplier_data = {}
        for detail in supplies_detail:
            name = detail['supply__counterparty__name']
            if name not in supplier_data:
                supplier_data[name] = {
                    'supplies': [], 'total_quantity': 0, 'total_sum': 0,
                    'supplies_count': 0, 'min_price': float('inf'), 'max_price': float('-inf'),
                }
            entry = supplier_data[name]
            entry['supplies'].append({
                'number': detail['supply__number'],
                'date': detail['supply__date'].isoformat(),
                'quantity': float(detail['quantity']),
                'price': float(detail['price']),
                'total': float(detail['total']),
            })
            entry['total_quantity'] += float(detail['quantity'])
            entry['total_sum'] += float(detail['total'])
            entry['supplies_count'] += 1
            entry['min_price'] = min(entry['min_price'], float(detail['price']))
            entry['max_price'] = max(entry['max_price'], float(detail['price']))

        suppliers_list = []
        for name, entry in supplier_data.items():
            if entry['min_price'] == float('inf'):
                entry['min_price'] = 0
            if entry['max_price'] == float('-inf'):
                entry['max_price'] = 0
            suppliers_list.append({
                'name': name,
                'supplies': sorted(entry['supplies'], key=lambda x: x['date'], reverse=True),
                'total_quantity': entry['total_quantity'],
                'total_sum': entry['total_sum'],
                'supplies_count': entry['supplies_count'],
                'min_price': entry['min_price'],
                'max_price': entry['max_price'],
                'avg_price': entry['total_sum'] / entry['total_quantity'] if entry['total_quantity'] > 0 else 0,
            })

        result.append({
            'raw_material__name': material['raw_material__name'],
            'raw_material__code': material['raw_material__code'] or '-',
            'raw_material__group': material['raw_material__group'],
            'raw_material__uom_name': material['raw_material__uom_name'],
            'total_quantity': float(material['total_quantity']),
            'total_sum': float(material['total_sum']),
            'avg_price': float(material['avg_price']) if material['avg_price'] else 0,
            'supplies_count': material['supplies_count'],
            'suppliers_count': material['suppliers_count'],
            'supplies': sum([s['supplies'] for s in suppliers_list], []),
            'suppliers': suppliers_list,
        })
    return result


def get_materials_list(
    page=1, page_size=10, search='', group='',
    start_date=None, end_date=None,
    sort_field='total_quantity', sort_order='desc',
):
    materials_query = RawMaterial.objects.filter(group__in=VALID_GROUPS)

    if search:
        search_query = Q()
        for word in search.split():
            search_query &= Q(name__icontains=word) | Q(code__icontains=word)
        materials_query = materials_query.filter(search_query)

    if group:
        materials_query = materials_query.filter(group=group)

    supplies_query = SupplyItem.objects.filter(raw_material__in=materials_query)
    supplies_query = apply_date_filter(supplies_query, start_date, end_date, 'supply__date')

    materials_data = materials_query.annotate(
        total_quantity=Coalesce(
            Sum('supplyitem__quantity', filter=Q(supplyitem__in=supplies_query)),
            0, output_field=DecimalField(),
        ),
        average_price=Coalesce(
            Avg('supplyitem__price', filter=Q(supplyitem__in=supplies_query)),
            0, output_field=DecimalField(),
        ),
        total_sum=Coalesce(
            Sum(
                F('supplyitem__quantity') * F('supplyitem__price'),
                filter=Q(supplyitem__in=supplies_query),
            ),
            0, output_field=DecimalField(),
        ),
        supplies_count=Count(
            'supplyitem__supply', filter=Q(supplyitem__in=supplies_query), distinct=True,
        ),
        suppliers_count=Count(
            'supplyitem__supply__counterparty', filter=Q(supplyitem__in=supplies_query), distinct=True,
        ),
    )

    if start_date or end_date:
        materials_data = materials_data.filter(
            Q(total_quantity__gt=0) | Q(total_sum__gt=0) | Q(supplies_count__gt=0)
        )

    stats = {
        'total_materials': materials_data.count(),
        'total_supplies': supplies_query.values('supply').distinct().count(),
        'total_suppliers': supplies_query.values('supply__counterparty').distinct().count(),
        'total_sum': float(
            supplies_query.aggregate(total=Sum(F('price') * F('quantity')))['total'] or 0
        ),
    }

    top_by_quantity = [
        {'name': m.name, 'quantity': float(m.total_quantity), 'supplies_count': m.supplies_count}
        for m in materials_data.order_by('-total_quantity')[:3]
    ]
    top_by_sum = [
        {'name': m.name, 'sum': float(m.total_sum), 'average_price': float(m.average_price)}
        for m in materials_data.order_by('-total_sum')[:3]
    ]

    sort_mapping = {
        'name': 'name', 'code': 'code', 'group': 'group',
        'total_quantity': 'total_quantity', 'average_price': 'average_price',
        'total_sum': 'total_sum', 'supplies_count': 'supplies_count',
        'suppliers_count': 'suppliers_count',
    }
    if sort_field in sort_mapping:
        prefix = '-' if sort_order == 'desc' else ''
        materials_data = materials_data.order_by(f'{prefix}{sort_mapping[sort_field]}')

    paginator = Paginator(materials_data, page_size)
    page_data = paginator.get_page(page)

    materials_list = [{
        'id': m.id, 'name': m.name, 'code': m.code or '-', 'group': m.group, 'uom': m.uom_name,
        'total_quantity': float(m.total_quantity), 'average_price': float(m.average_price),
        'total_sum': float(m.total_sum), 'supplies_count': m.supplies_count,
        'suppliers_count': m.suppliers_count,
    } for m in page_data]

    return {
        'materials': materials_list,
        'total': paginator.count,
        'stats': stats,
        'top_by_quantity': top_by_quantity,
        'top_by_sum': top_by_sum,
        'available_groups': VALID_GROUPS,
    }


def get_material_details(material_id, start_date=None, end_date=None):
    try:
        material = RawMaterial.objects.get(id=material_id)
    except RawMaterial.DoesNotExist:
        raise NotFoundError("Материал не найден")

    supplies_query = (
        SupplyItem.objects
        .filter(raw_material=material)
        .select_related('supply', 'supply__counterparty')
    )
    supplies_query = apply_date_filter(supplies_query, start_date, end_date, 'supply__date')

    stats = supplies_query.aggregate(
        total_supplies=Count('supply', distinct=True),
        total_quantity=Sum('quantity'),
        total_sum=Sum(F('quantity') * F('price')),
        min_price=Min('price'),
        max_price=Max('price'),
        avg_price=Avg('price'),
    )

    suppliers_data = (
        supplies_query
        .values('supply__counterparty__id', 'supply__counterparty__name')
        .annotate(
            total_supplies=Count('supply', distinct=True),
            total_quantity=Sum('quantity'),
            total_sum=Sum(F('quantity') * F('price')),
            min_price=Min('price'),
            max_price=Max('price'),
            avg_price=Avg('price'),
        )
        .order_by('-total_quantity')
    )

    monthly_data = (
        supplies_query
        .annotate(month=TruncMonth('supply__date'))
        .values('month')
        .annotate(quantity=Sum('quantity'), avg_price=Avg('price'))
        .order_by('month')
    )

    supplies_history = (
        supplies_query
        .order_by('-supply__date')
        .values('supply__number', 'supply__date', 'supply__counterparty__name', 'quantity', 'price')
        [:1000]
    )

    return {
        'material': {
            'id': material.id, 'name': material.name, 'code': material.code,
            'group': material.group, 'uom': material.uom_name,
        },
        'statistics': {
            'total_supplies': stats['total_supplies'] or 0,
            'total_quantity': float(stats['total_quantity'] or 0),
            'total_sum': float(stats['total_sum'] or 0),
            'price_range': {
                'min': float(stats['min_price'] or 0),
                'max': float(stats['max_price'] or 0),
                'avg': float(stats['avg_price'] or 0),
            },
        },
        'suppliers': [{
            'id': s['supply__counterparty__id'],
            'name': s['supply__counterparty__name'],
            'total_supplies': s['total_supplies'],
            'total_quantity': float(s['total_quantity']),
            'total_sum': float(s['total_sum']),
            'price_range': {
                'min': float(s['min_price']),
                'max': float(s['max_price']),
                'avg': float(s['avg_price'] or 0),
            },
        } for s in suppliers_data],
        'monthly_data': [{
            'month': d['month'].strftime('%Y-%m'),
            'quantity': float(d['quantity'] or 0),
            'avg_price': float(d['avg_price'] or 0),
        } for d in monthly_data],
        'supply_history': [{
            'number': item['supply__number'],
            'date': item['supply__date'].strftime('%d.%m.%Y'),
            'supplier': item['supply__counterparty__name'],
            'quantity': float(item['quantity']),
            'price': float(item['price']),
            'total': float(item['quantity'] * item['price']),
        } for item in supplies_history],
    }


def get_suppliers_list(
    page=1, page_size=10, search='',
    start_date=None, end_date=None,
    sort_field='supplies_count', sort_order='desc',
):
    suppliers_query = Counterparty.objects.filter(supply__isnull=False).distinct()

    if search:
        search_query = Q()
        for word in search.split():
            search_query &= Q(name__icontains=word)
        suppliers_query = suppliers_query.filter(search_query)

    supplies_filter = Q()
    date_filter = Q()

    if start_date or end_date:
        moscow_tz = pytz.timezone('Europe/Moscow')
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                start_moscow = moscow_tz.localize(datetime.combine(start, datetime.min.time()))
                date_filter &= Q(date__gte=start_moscow)
                supplies_filter &= Q(supply__date__gte=start_moscow)
            except ValueError:
                pass
        if end_date:
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                end_moscow = moscow_tz.localize(datetime.combine(end, datetime.min.time()))
                date_filter &= Q(date__lt=end_moscow)
                supplies_filter &= Q(supply__date__lt=end_moscow)
            except ValueError:
                pass

    sum_subquery = Supply.objects.filter(counterparty=OuterRef('pk'))
    if date_filter:
        sum_subquery = sum_subquery.filter(date_filter)
    sum_subquery = sum_subquery.values('counterparty').annotate(total=Sum('sum')).values('total')

    suppliers_data = suppliers_query.annotate(
        supplies_count=Count('supply', filter=supplies_filter, distinct=True),
        total_sum=Subquery(sum_subquery),
        positions_count=Count('supply__items', filter=supplies_filter, distinct=True),
        unique_materials=Count('supply__items__raw_material', filter=supplies_filter, distinct=True),
        last_supply=Max('supply__date'),
    ).annotate(
        avg_supply_sum=Case(
            When(
                supplies_count__gt=0,
                then=ExpressionWrapper(
                    F('total_sum') / F('supplies_count'),
                    output_field=DecimalField(max_digits=20, decimal_places=2),
                ),
            ),
            default=Value(0, output_field=DecimalField(max_digits=20, decimal_places=2)),
        )
    )

    supplies_query_stats = Supply.objects.filter(counterparty__in=suppliers_data)
    if date_filter:
        supplies_query_stats = supplies_query_stats.filter(date_filter)

    stats = {
        'total_suppliers': suppliers_data.count(),
        'total_supplies': supplies_query_stats.count(),
        'total_positions': SupplyItem.objects.filter(supply__in=supplies_query_stats).count(),
        'total_sum': float(suppliers_data.aggregate(total=Sum('total_sum'))['total'] or 0),
    }

    sort_mapping = {
        'name': 'name', 'supplies_count': 'supplies_count', 'total_sum': 'total_sum',
        'positions_count': 'positions_count', 'last_supply': 'last_supply',
    }
    if sort_field in sort_mapping:
        prefix = '-' if sort_order == 'desc' else ''
        suppliers_data = suppliers_data.order_by(f'{prefix}{sort_mapping[sort_field]}')

    paginator = Paginator(suppliers_data, page_size)
    page_data = paginator.get_page(page)

    suppliers_list = [{
        'id': s.id, 'name': s.name,
        'supplies_count': s.supplies_count,
        'total_sum': float(s.total_sum or 0),
        'positions_count': s.positions_count,
        'unique_materials': s.unique_materials,
        'last_supply': s.last_supply.isoformat() if s.last_supply else None,
        'avg_supply_sum': float(s.avg_supply_sum or 0),
    } for s in page_data]

    return {
        'suppliers': suppliers_list,
        'total': paginator.count,
        'stats': stats,
    }


def get_supplier_details(supplier_id, start_date=None, end_date=None, material_id=None):
    try:
        supplier = Counterparty.objects.get(id=supplier_id)
    except Counterparty.DoesNotExist:
        raise NotFoundError("Поставщик не найден")

    supplies_query = Supply.objects.filter(counterparty=supplier)
    if start_date:
        supplies_query = supplies_query.filter(date__gte=start_date)
    if end_date:
        supplies_query = supplies_query.filter(date__lte=end_date)

    total_sum = supplies_query.aggregate(sum=Sum('sum'))['sum'] or 0

    items_query = (
        SupplyItem.objects
        .filter(supply__in=supplies_query)
        .select_related('raw_material', 'supply', 'supply__counterparty')
    )
    if material_id:
        items_query = items_query.filter(raw_material_id=material_id)

    supplies_count = supplies_query.count()
    stats = {
        'total_sum': float(total_sum),
        'positions_count': items_query.count(),
        'unique_materials': items_query.values('raw_material').distinct().count(),
        'avg_supply_sum': float(total_sum / supplies_count if supplies_count > 0 else 0),
    }

    materials_by_category = {}
    materials_data = {}

    for item in items_query:
        material = item.raw_material
        category = material.group or 'Без категории'

        if category not in materials_by_category:
            materials_by_category[category] = []

        if material.id not in materials_data:
            materials_data[material.id] = {
                'id': material.id, 'name': material.name, 'code': material.code,
                'uom': material.uom_name, 'group': category,
                'total_quantity': 0, 'total_sum': 0,
                'supplies': [], 'price_history': [], 'suppliers': {},
            }
            materials_by_category[category].append(material.id)

        mat = materials_data[material.id]
        mat['total_quantity'] += float(item.quantity)
        mat['total_sum'] += float(item.total)
        mat['supplies'].append({
            'date': item.supply.date.strftime('%d.%m.%Y'),
            'quantity': float(item.quantity),
            'price': float(item.price),
            'total': float(item.total),
        })
        mat['price_history'].append({
            'date': item.supply.date.strftime('%Y-%m-%d'),
            'price': float(item.price),
        })

        cp = item.supply.counterparty
        if cp.id not in mat['suppliers']:
            mat['suppliers'][cp.id] = {
                'id': cp.id, 'name': cp.name, 'supplies_count': 0,
                'total_quantity': 0, 'total_sum': 0,
                'min_price': float('inf'), 'max_price': float('-inf'),
                'uom': material.uom_name,
            }

        sd = mat['suppliers'][cp.id]
        sd['supplies_count'] += 1
        sd['total_quantity'] += float(item.quantity)
        sd['total_sum'] += float(item.total)
        sd['min_price'] = min(sd['min_price'], float(item.price))
        sd['max_price'] = max(sd['max_price'], float(item.price))

    categories_data = {}
    for category, material_ids in materials_by_category.items():
        category_sum = 0
        materials = []
        for mat_id in material_ids:
            mat = materials_data[mat_id]
            avg_price = mat['total_sum'] / mat['total_quantity'] if mat['total_quantity'] > 0 else 0

            mat['price_history'].sort(key=lambda x: x['date'])
            mat['supplies'].sort(key=lambda x: x['date'], reverse=True)

            mat['suppliers'] = list(mat['suppliers'].values())
            for s in mat['suppliers']:
                if s['min_price'] == float('inf'):
                    s['min_price'] = 0
                if s['max_price'] == float('-inf'):
                    s['max_price'] = 0
                s['avg_price'] = s['total_sum'] / s['total_quantity'] if s['total_quantity'] > 0 else 0

            mat['avg_price'] = float(avg_price)
            mat['last_price'] = float(mat['supplies'][0]['price']) if mat['supplies'] else 0

            materials.append(mat)
            category_sum += mat['total_sum']

        categories_data[category] = {'materials': materials, 'total_sum': float(category_sum)}

    available_materials = sorted(
        [
            {'id': m['id'], 'name': m['name'], 'code': m['code'], 'group': m['group']}
            for m in materials_data.values()
        ],
        key=lambda x: x['name'],
    )

    supply_history_qs = (
        supplies_query
        .order_by('-date')
        .prefetch_related('items__raw_material')
        .values('id', 'number', 'date', 'sum')
        .annotate(items_count=Count('items'))
    )

    formatted_supply_history = []
    for supply in supply_history_qs:
        supply_items = (
            SupplyItem.objects
            .filter(supply_id=supply['id'])
            .select_related('raw_material')
        )
        formatted_supply_history.append({
            'id': supply['id'],
            'number': supply['number'],
            'date': supply['date'].strftime('%d.%m.%Y'),
            'items_count': supply['items_count'],
            'sum': float(supply['sum']),
            'items': [{
                'id': item.id,
                'material_name': item.raw_material.name,
                'material_group': item.raw_material.group,
                'quantity': float(item.quantity),
                'price': float(item.price),
                'total': float(item.total),
                'uom': item.raw_material.uom_name,
            } for item in supply_items],
        })

    return {
        'supplier': {'id': supplier.id, 'name': supplier.name},
        'statistics': stats,
        'categories': categories_data,
        'available_materials': available_materials,
        'supply_history': formatted_supply_history,
    }
