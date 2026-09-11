from django.http import JsonResponse
from django.db.models import Sum, Count, Min, Max
from rest_framework.decorators import api_view
from datetime import datetime
from django.utils.dateparse import parse_date
from django.utils import timezone

from core.models import Product, ShipmentItem, RawMaterialUsage
from api.exceptions import NotFoundError, DataProcessingError
from api.serializers import ListQuerySerializer
from api.services.product_service import (
    aggregated_products, get_product_filters, get_products_list, period_bounds,
)

import logging
logger = logging.getLogger(__name__)


@api_view(['GET'])
def product_data(request):
    """API endpoint для получения данных по товарам с фильтрацией"""
    params = ListQuerySerializer.from_query_params(
        request.query_params,
        default_sort_field='total_quantity',
        allowed_sort_fields={
            'name', 'subgroup', 'quantity', 'total_quantity',
            'average_price', 'total_sum', 'shipments_count',
        },
    )
    try:
        data = get_products_list(
            page=params['page'],
            page_size=params['page_size'],
            search=params['search'].strip(),
            subgroup=params['subgroup'].strip(),
            sales_channel=params['sales_channel'].strip(),
            start_date=params.get('start_date'),
            end_date=params.get('end_date'),
            sort_field=params['sort_field'],
            sort_order=params['sort_order'],
        )
        return JsonResponse({'status': 'success', 'data': data})

    except Exception as e:
        logger.error(f"Error in product_data: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения данных по товарам")


@api_view(['GET'])
def product_details(request, product_id):
    """API endpoint для получения детальной информации о товаре"""
    try:
        # Получаем базовую информацию о товаре
        product = Product.objects.get(id=product_id)
        
        # Получаем параметры фильтрации по датам
        start_date = request.GET.get('startDate')
        end_date = request.GET.get('endDate')
        sales_channel = request.GET.get('salesChannel', '').strip()

        # Базовый QuerySet для отгрузок
        shipments_query = ShipmentItem.objects.filter(
            product=product
        ).select_related('shipment')

        if sales_channel:
            shipments_query = shipments_query.filter(
                shipment__sales_channel__name=sales_channel
            )

        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
                start_date = timezone.make_aware(start_date, timezone.get_current_timezone())
                shipments_query = shipments_query.filter(
                    shipment__date__gte=start_date
                )
            except ValueError:
                pass

        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
                # Make end_date inclusive by adding 23:59:59
                end_date = end_date.replace(hour=23, minute=59, second=59)
                end_date = timezone.make_aware(end_date, timezone.get_current_timezone())
                shipments_query = shipments_query.filter(
                    shipment__date__lte=end_date
                )
            except ValueError:
                pass

        # Получаем общую статистику
        stats = {}
        stats_data = shipments_query.aggregate(
            total_shipments=Count('shipment', distinct=True),
            total_quantity=Sum('quantity'),
            min_price=Min('price'),
            max_price=Max('price')
        )
        # Отдельно считаем total_revenue
        total_revenue = sum(item.quantity * item.price for item in shipments_query)
        stats.update(stats_data)

        # Получаем используемые материалы
        materials = RawMaterialUsage.objects.filter(
            shipment_item__in=shipments_query
        ).values(
            'raw_material__name',
            'raw_material__uom_name'
        ).annotate(
            total_quantity=Sum('quantity')
        ).order_by('raw_material__name')

        # Получаем историю отгрузок
        shipments_history = list(shipments_query.order_by('-shipment__date')[:1000])
        
        # Получаем динамику по месяцам
        monthly_data = {}
        for item in shipments_query:
            month = item.shipment.date.replace(day=1)
            if month not in monthly_data:
                monthly_data[month] = {'quantity': 0, 'revenue': 0}
            monthly_data[month]['quantity'] += item.quantity
            monthly_data[month]['revenue'] += item.quantity * item.price

        monthly_dynamics = [
            {
                'month': month,
                'quantity': data['quantity'],
                'revenue': data['revenue']
            }
            for month, data in sorted(monthly_data.items())
        ]

        response_data = {
            'product': {
                'id': product.id,
                'name': product.name,
                'group': product.group,
                'subgroup': product.subgroup
            },
            'statistics': {
                'total_shipments': stats['total_shipments'] or 0,
                'total_quantity': float(stats['total_quantity'] or 0),
                'total_revenue': float(total_revenue),
                'average_quantity': (
                    float(stats['total_quantity'] or 0) / stats['total_shipments'] 
                    if stats['total_shipments'] 
                    else 0
                ),
                'price_range': {
                    'min': float(stats['min_price'] or 0),
                    'max': float(stats['max_price'] or 0)
                }
            },
            'materials': [{
                'name': material['raw_material__name'],
                'quantity': float(material['total_quantity']),
                'unit': material['raw_material__uom_name']
            } for material in materials],
            'shipments_history': [{
                'number': item.shipment.number,
                'date': timezone.localtime(item.shipment.date).isoformat(),
                'quantity': float(item.quantity),
                'price': float(item.price),
                'total': float(item.quantity * item.price)
            } for item in shipments_history],
            'monthly_dynamics': [{
                'month': month.isoformat(),
                'quantity': float(data['quantity']),
                'revenue': float(data['revenue'])
            } for month, data in sorted(monthly_data.items())]
        }

        return JsonResponse({
            'status': 'success',
            'data': response_data
        })

    except Product.DoesNotExist:
        raise NotFoundError("Товар не найден")
    except Exception as e:
        logger.error(f"Error in product_details: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения детальной информации о товаре")


# Добавим новые импорты
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from datetime import datetime
from django.utils.dateparse import parse_date

@api_view(['GET'])
def export_products_excel(request):
    """API endpoint для экспорта товаров в Excel"""
    try:
        # Те же параметры и тот же расчёт, что и на экране раздела:
        # выгрузка обязана показывать ровно то, что человек видит.
        since, until = period_bounds(
            parse_date(request.GET.get('startDate') or ''),
            parse_date(request.GET.get('endDate') or ''),
        )
        _, products_data = aggregated_products(
            search=request.GET.get('search', '').strip(),
            subgroup=request.GET.get('subgroup', '').strip(),
            sales_channel=request.GET.get('salesChannel', '').strip(),
            since=since,
            until=until,
        )

        # Создаем новый Excel-файл
        wb = Workbook()
        ws = wb.active
        ws.title = "Товары"

        # Заголовки
        headers = [
            'Товар', 
            'Подгруппа', 
            'Количество', 
            'Средняя цена', 
            'Сумма продаж',
            'Количество отгрузок'
        ]

        # Стили для заголовков
        header_font = Font(bold=True)
        header_alignment = Alignment(horizontal='center')

        # Записываем заголовки
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.alignment = header_alignment

        # Записываем данные
        for row, product in enumerate(products_data, 2):
            ws.cell(row=row, column=1, value=product.name)
            ws.cell(row=row, column=2, value=product.subgroup)
            ws.cell(row=row, column=3, value=float(product.total_quantity))
            ws.cell(row=row, column=4, value=float(product.average_price))
            ws.cell(row=row, column=5, value=float(product.total_sum))
            ws.cell(row=row, column=6, value=product.shipments_count)

        # Автоматическая ширина колонок
        for column_cells in ws.columns:
            max_length = 0
            column = column_cells[0].column_letter
            for cell in column_cells:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except (TypeError, AttributeError):
                    pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column].width = adjusted_width

        # Создаем HTTP-ответ
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename=products_export.xlsx'

        # Сохраняем файл
        wb.save(response)

        return response

    except Exception as e:
        logger.error(f"Error in export_products_excel: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка экспорта товаров в Excel")


@api_view(['GET'])
def product_filters(request):
    """Справочники для панели фильтров раздела."""
    try:
        return JsonResponse({'status': 'success', 'data': get_product_filters()})
    except Exception as e:
        logger.error(f"Error in product_filters: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения справочников товаров")
