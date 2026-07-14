# api/views/materials.py

from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, F, Sum, Count
from django.db.models.functions import TruncMonth
from datetime import datetime
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.models import (
    RawMaterial,
    RawMaterialUsage,
    Counterparty,
    SupplyItem
)
from api.exceptions import NotFoundError, DataProcessingError

import logging
logger = logging.getLogger(__name__)

def material_data(request):
    """API endpoint для получения данных о материалах с фильтрацией"""
    try:
        # Определяем допустимые группы
        VALID_GROUPS = [
            'Тара',
            'Материалы для производства',
            'Этикетки'
        ]
       
        # Получаем параметры фильтрации
        MAX_PAGE_SIZE = 500  # Защита от DoS через огромный page_size
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('pageSize', 10)), MAX_PAGE_SIZE)
        search = request.GET.get('search', '').strip()
        group = request.GET.get('group', '').strip()
        start_date = request.GET.get('startDate')
        end_date = request.GET.get('endDate')
        counterparties = request.GET.getlist('counterparties', [])
        sort_field = request.GET.get('sortField', 'name')
        sort_order = request.GET.get('sortOrder', 'desc')

        # Базовый QuerySet для материалов
        materials_query = RawMaterial.objects.filter(group__in=VALID_GROUPS)

        # Промежуточный QuerySet для отслеживания фильтрации
        filtered_materials = materials_query

        # Фильтр по поиску (case-insensitive)
        if search:
            search_words = search.split()
            search_query = Q()
            for word in search_words:
                word_query = (
                    Q(name__icontains=word) |
                    Q(code__icontains=word) |
                    Q(article__icontains=word)
                )
                search_query &= word_query
            filtered_materials = filtered_materials.filter(search_query)

        # Фильтр по группе
        if group:
            filtered_materials = filtered_materials.filter(group=group)

        # Фильтр по контрагентам
        if counterparties:
            materials_supplied = RawMaterial.objects.filter(
                supplyitem__supply__counterparty__id__in=counterparties
            ).distinct()
            filtered_materials = filtered_materials.filter(id__in=materials_supplied.values_list('id', flat=True))

        # Формируем списки с подсчетом данных для каждого материала
        materials_data = []
        
        for material in filtered_materials:
            # Подзапрос для usage с учетом всех фильтров
            usage_query = RawMaterialUsage.objects.filter(raw_material=material)
            
            # Фильтр по датам
            if start_date:
                parsed_start_date = parse_date(start_date)
                if parsed_start_date:
                    usage_query = usage_query.filter(
                        shipment_item__shipment__date__gte=parsed_start_date
                    )

            if end_date:
                parsed_end_date = parse_date(end_date)
                if parsed_end_date:
                    usage_query = usage_query.filter(
                        shipment_item__shipment__date__lte=parsed_end_date
                    )

            # Получаем агрегированные данные
            usage_data = usage_query.aggregate(
                total_usage=Sum('quantity'),
                shipments_count=Count('shipment_item__shipment', distinct=True)
            )

            supply_items_query = SupplyItem.objects.filter(
                raw_material=material
            )

            if counterparties:
                supply_items_query = supply_items_query.filter(
                    supply__counterparty__id__in=counterparties
                )
            if start_date:
                parsed_start_date = parse_date(start_date)
                if parsed_start_date:
                    supply_items_query = supply_items_query.filter(supply__date__gte=parsed_start_date)
            if end_date:
                parsed_end_date = parse_date(end_date)
                if parsed_end_date:
                    supply_items_query = supply_items_query.filter(supply__date__lte=parsed_end_date)

            suppliers_count = supply_items_query.values('supply__counterparty').distinct().count()
            supplied_quantity = supply_items_query.aggregate(total=Sum('quantity'))['total']
            total_quantity = supplied_quantity if (counterparties or start_date or end_date) else usage_data['total_usage']

            materials_data.append({
                'id': material.id,
                'name': material.name,
                'code': material.code or '-',
                'group': material.group,
                'uom': material.uom_name,
                'total_usage': float(total_quantity or 0),
                'shipments_count': usage_data['shipments_count'],
                'suppliers_count': suppliers_count
            })

        # Сортировка данных
        # Priority for groups: production materials first, then containers, then labels
        GROUP_PRIORITY = {
            'Материалы для производства': 0,
            'Тара': 1,
            'Этикетки': 2
        }

        def get_sort_key(item):
            # Check for exact name match (case-insensitive)
            is_exact_match = item['name'].lower().strip() == search.lower().strip() if search else False
            group_priority = GROUP_PRIORITY.get(item['group'], 99)

            if sort_field in ['total_usage', 'shipments_count', 'suppliers_count']:
                field_value = float(item[sort_field] or 0)
                # For numeric fields: exact match first, then group priority, then field value
                if sort_order == 'desc':
                    return (not is_exact_match, group_priority, -field_value)
                else:
                    return (not is_exact_match, group_priority, field_value)
            else:
                field_value = item.get(sort_field, '')
                # For text fields: exact match first, then group priority, then name
                return (not is_exact_match, group_priority, field_value.lower() if isinstance(field_value, str) else field_value)

        materials_data.sort(key=get_sort_key)

        # Пагинация результатов
        paginator = Paginator(materials_data, page_size)
        page_data = paginator.get_page(page)

        # Статистика с учетом всех фильтров
        stats = {
            'Материалы для производства': len([m for m in materials_data if m['group'] == 'Материалы для производства']),
            'Тара': len([m for m in materials_data if m['group'] == 'Тара']),
            'Этикетки': len([m for m in materials_data if m['group'] == 'Этикетки'])
        }

        # Получаем список контрагентов только для отфильтрованных материалов
        counterparties_list = Counterparty.objects.filter(
            supply__items__raw_material__in=filtered_materials
        ).distinct().values('id', 'name').order_by('name')

        return JsonResponse({
            'status': 'success',
            'data': {
                'materials': list(page_data),
                'total': len(materials_data),
                'stats': stats,
                'available_groups': VALID_GROUPS,
                'counterparties': list(counterparties_list)
            }
        })

    except Exception as e:
        logger.error(f"Error in material_data: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения данных о материалах")

def material_details(request, material_id):
    """API endpoint для получения детальной информации о материале"""
    try:
        material = RawMaterial.objects.get(id=material_id)

        # Получаем параметры фильтрации по датам
        start_date = request.GET.get('startDate')
        end_date = request.GET.get('endDate')
        counterparties = request.GET.getlist('counterparties', [])

        # Базовый QuerySet для использования материала
        usages = RawMaterialUsage.objects.filter(raw_material=material)
        
        # Применяем фильтры по датам
        if start_date:
            try:
                start_date = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
                usages = usages.filter(
                    shipment_item__shipment__date__gte=start_date
                )
            except ValueError as e:
                logger.error(f"Error parsing start_date: {e}")
                pass

        if end_date:
            try:
                end_date = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d'))
                usages = usages.filter(
                    shipment_item__shipment__date__lte=end_date
                )
            except ValueError as e:
                logger.error(f"Error parsing end_date: {e}")
                pass

        # Получаем статистику использования
        total_usage = usages.aggregate(total=Sum('quantity'))['total'] or 0
        total_shipments = usages.values('shipment_item__shipment').distinct().count()
        total_products = usages.values('shipment_item__product').distinct().count()

        # Получаем все поставки для материала с учетом дат
        supplies = SupplyItem.objects.filter(
            raw_material=material
        )
        if counterparties:
            supplies = supplies.filter(supply__counterparty__id__in=counterparties)
        if start_date:
            supplies = supplies.filter(supply__date__gte=start_date)
        if end_date:
            supplies = supplies.filter(supply__date__lte=end_date)
            
        supplies = supplies.select_related('supply__counterparty').order_by('-supply__date')

        # Группируем данные по поставщикам
        suppliers_data = {}
        for supply in supplies:
            supplier_id = supply.supply.counterparty.id
            if supplier_id not in suppliers_data:
                suppliers_data[supplier_id] = {
                    'name': supply.supply.counterparty.name,
                    'total_supplies': 0,
                    'total_quantity': 0,
                    'total_sum': 0,
                    'prices': [],
                    'last_supplies': []
                }

            supplier = suppliers_data[supplier_id]
            supplier['total_supplies'] += 1
            supplier['total_quantity'] += float(supply.quantity)
            supplier['total_sum'] += float(supply.total)
            supplier['prices'].append(float(supply.price))

            if len(supplier['last_supplies']) < 3:
                supplier['last_supplies'].append({
                    'date': supply.supply.date.strftime('%d.%m.%Y'),
                    'quantity': float(supply.quantity),
                    'price': float(supply.price)
                })

        # Формируем список поставщиков
        suppliers_list = []
        for supplier_data in suppliers_data.values():
            prices = supplier_data.pop('prices', [])
            avg_price = (supplier_data['total_sum'] / supplier_data['total_quantity']
                        if supplier_data['total_quantity'] > 0 else 0)

            suppliers_list.append({
                'name': supplier_data['name'],
                'total_supplies': supplier_data['total_supplies'],
                'total_quantity': supplier_data['total_quantity'],
                'avg_price': avg_price,
                'price_range': [min(prices), max(prices)] if prices else [avg_price, avg_price],
                'last_supplies': supplier_data['last_supplies']
            })

        # Получаем динамику использования по месяцам
        monthly_usage = (
            usages
            .annotate(month=TruncMonth('shipment_item__shipment__date'))
            .values('month')
            .annotate(quantity=Sum('quantity'))
            .order_by('month')
        )

        # Получаем использование в продуктах
        product_usage = (
            usages
            .values(
                'shipment_item__product__id',
                'shipment_item__product__name'
            )
            .annotate(quantity=Sum('quantity'))
            .order_by('-quantity')
        )

        # Получаем историю использования
        usage_history = (
            usages
            .select_related(
                'shipment_item__shipment',
                'shipment_item__product'
            )
            .annotate(
                shipment_number=F('shipment_item__shipment__number'),
                shipment_date=F('shipment_item__shipment__date'),
                product_name=F('shipment_item__product__name')
            )
            .values(
                'shipment_number',
                'shipment_date',
                'product_name',
                'quantity'
            )
            .order_by('-shipment_date')[:100]
        )

        return JsonResponse({
            'status': 'success',
            'data': {
                'material': {
                    'id': material.id,
                    'name': material.name,
                    'code': material.code,
                    'group': material.group,
                    'uom': material.uom_name
                },
                'statistics': {
                    'total_usage': float(total_usage),
                    'total_shipments': total_shipments,
                    'total_products': total_products
                },
                'suppliers': suppliers_list,
                'monthly_usage': [
                    {
                        'month': item['month'].strftime('%Y-%m'),
                        'quantity': float(item['quantity'])
                    }
                    for item in monthly_usage
                ],
                'product_usage': [
                    {
                        'id': item['shipment_item__product__id'],
                        'name': item['shipment_item__product__name'],
                        'quantity': float(item['quantity'])
                    }
                    for item in product_usage
                ],
                'usage_history': [
                    {
                        'shipment_number': item['shipment_number'],
                        'date': item['shipment_date'].strftime('%d.%m.%Y'),
                        'product_name': item['product_name'],
                        'quantity': float(item['quantity'])
                    }
                    for item in usage_history
                ]
            }
        })

    except RawMaterial.DoesNotExist:
        raise NotFoundError("Материал не найден")
    except Exception as e:
        logger.error(f"Error in material_details: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения детальной информации о материале")
