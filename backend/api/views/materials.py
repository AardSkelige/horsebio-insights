# api/views/materials.py

from django.http import JsonResponse
from django.db.models import F, Sum
from django.db.models.functions import TruncMonth
from datetime import datetime
from django.utils import timezone

from core.models import RawMaterial, RawMaterialUsage, SupplyItem
from api.exceptions import NotFoundError, DataProcessingError
from api.services.material_service import get_material_filters, get_materials_list

import logging
logger = logging.getLogger(__name__)


def material_data(request):
    """API endpoint для получения данных о материалах с фильтрацией"""
    try:
        MAX_PAGE_SIZE = 500  # Защита от DoS через огромный page_size
        data = get_materials_list(
            page=int(request.GET.get('page', 1)),
            page_size=min(int(request.GET.get('pageSize', 10)), MAX_PAGE_SIZE),
            search=request.GET.get('search', '').strip(),
            group=request.GET.get('group', '').strip(),
            start_date=request.GET.get('startDate'),
            end_date=request.GET.get('endDate'),
            counterparties=request.GET.getlist('counterparties', []),
            sort_field=request.GET.get('sortField', 'name'),
            # По умолчанию сортируем по имени, а значит — по возрастанию:
            # обратный алфавит в качестве первого экрана никому не нужен.
            # Таблица раздела всегда присылает направление сама, умолчание
            # достаётся вызовам без параметров вроде подбора материала
            # в закупках.
            sort_order=request.GET.get('sortOrder', 'asc'),
        )
        return JsonResponse({'status': 'success', 'data': data})
    except Exception as e:
        logger.error(f"Error in material_data: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения данных о материалах")


def material_filters(request):
    """Справочники для панели фильтров раздела."""
    try:
        return JsonResponse({'status': 'success', 'data': get_material_filters()})
    except Exception as e:
        logger.error(f"Error in material_filters: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения справочников материалов")


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
