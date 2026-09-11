from django.http import JsonResponse
from django.db.models import F, Sum, DecimalField
from django.db.models.functions import TruncMonth
from rest_framework.decorators import api_view
from decimal import Decimal
from datetime import datetime
from django.utils import timezone

from core.models import (
   Shipment,
   ShipmentItem, 
   Counterparty
)
from forecasting.services.categorization.categorizer import CounterpartyCategorizator
from django.utils import timezone
from datetime import timedelta
from rest_framework.response import Response
from api.exceptions import NotFoundError, DataProcessingError, ValidationError
from api.serializers import ListQuerySerializer
from api.services.counterparty_service import get_counterparties_list

import logging
logger = logging.getLogger(__name__)


@api_view(['GET'])
def counterparty_data(request):
    """API endpoint для получения данных по контрагентам с фильтрацией и пагинацией"""
    params = ListQuerySerializer.from_query_params(
        request.query_params,
        default_sort_field='total_sales',
        allowed_sort_fields={
            'name', 'total_sales', 'shipments_count',
            'total_products', 'last_shipment',
        },
    )
    try:
        data = get_counterparties_list(
            page=params['page'],
            page_size=params['page_size'],
            search=params['search'].strip(),
            start_date=params.get('start_date'),
            end_date=params.get('end_date'),
            sort_field=params['sort_field'],
            sort_order=params['sort_order'],
        )
        return JsonResponse({'status': 'success', 'data': data})

    except Exception as e:
        logger.error(f"Error in counterparty_data: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения данных по контрагентам")


@api_view(['GET'])
def counterparty_details(request, counterparty_id):
    """API endpoint для получения детальной информации о контрагенте"""
    try:
        # Получаем параметры фильтрации дат
        start_date = request.GET.get('startDate')
        end_date = request.GET.get('endDate')

        counterparty = Counterparty.objects.get(id=counterparty_id)
        
        # Базовый queryset отгрузок с учетом фильтров по датам
        shipments = Shipment.objects.filter(counterparty=counterparty)
        
        if start_date and end_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
                start_date = timezone.make_aware(start_date, timezone.get_current_timezone())
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
                end_date = timezone.make_aware(end_date, timezone.get_current_timezone())
                shipments = shipments.filter(
                    date__gte=start_date,
                    date__lte=end_date
                )
            except ValueError as e:
                logger.error(f"Error parsing dates: {str(e)}")
                # Если даты некорректны, используем весь период
                pass

        # Получаем все позиции отгрузок для данного контрагента
        shipment_items = ShipmentItem.objects.filter(shipment__in=shipments)

        # Статистика
        statistics = {
            'total_shipments': shipments.count(),
            'total_products': shipment_items.count(),
            'unique_products': shipment_items.values('product').distinct().count()
        }

        # Топ-5 по количеству
        quantity_data = (shipment_items
            .values('product__id', 'product__name', 'quantity', 'shipment')
            .order_by('product__id'))

        product_quantities = {}
        for item in quantity_data:
            prod_id = item['product__id']
            if prod_id not in product_quantities:
                product_quantities[prod_id] = {
                    'name': item['product__name'],
                    'quantity': Decimal('0'),
                    'shipments': set()
                }
            product_quantities[prod_id]['quantity'] += item['quantity']
            product_quantities[prod_id]['shipments'].add(item['shipment'])

        top_by_quantity = sorted(
            [
                {
                    'name': data['name'],
                    'quantity': float(data['quantity']),
                    'shipments_count': len(data['shipments'])
                }
                for data in product_quantities.values()
            ],
            key=lambda x: x['quantity'],
            reverse=True
        )[:5]

        # Топ-5 по выручке
        revenue_data = shipment_items.values(
            'product__id', 
            'product__name', 
            'quantity',
            'price'
        ).order_by('product__id')

        product_revenue = {}
        for item in revenue_data:
            prod_id = item['product__id']
            if prod_id not in product_revenue:
                product_revenue[prod_id] = {
                    'name': item['product__name'],
                    'revenue': Decimal('0'),
                    'quantity': Decimal('0')
                }
            quantity = Decimal(str(item['quantity']))
            price = Decimal(str(item['price']))
            product_revenue[prod_id]['revenue'] += quantity * price
            product_revenue[prod_id]['quantity'] += quantity

        top_by_revenue = sorted(
            [
                {
                    'name': data['name'],
                    'revenue': float(data['revenue']),
                    'price_per_unit': float(data['revenue'] / data['quantity'] if data['quantity'] else 0)
                }
                for data in product_revenue.values()
            ],
            key=lambda x: x['revenue'],
            reverse=True
        )[:5]

        # Динамика по месяцам с учетом фильтрации
        monthly_data = shipments.values(
            'date'
        ).annotate(
            month=TruncMonth('date')
        ).values(
            'month'
        ).annotate(
            quantity=Sum('items__quantity'),
            revenue=Sum(F('items__quantity') * F('items__price'), output_field=DecimalField())
        ).order_by('month')

        monthly_dynamics = [
            {
                'month': item['month'].isoformat(),
                'quantity': float(item['quantity']),
                'revenue': float(item['revenue'])
            }
            for item in monthly_data
        ]

        # История отгрузок
        recent_shipments = (shipments
            .prefetch_related(
                'items__product',
                'items__raw_material_usages__raw_material'
            )
            .order_by('-date')[:1000])

        shipment_history = []
        for shipment in recent_shipments:
            shipment_data = {
                'number': shipment.number,
                'date': timezone.localtime(shipment.date).isoformat(),
                'items': []
            }
            
            for item in shipment.items.all():
                item_data = {
                    'product_name': item.product.name,
                    'quantity': float(item.quantity),
                    'materials': [{
                        'name': usage.raw_material.name,
                        'quantity': float(usage.quantity),
                        'uom': usage.raw_material.uom_name
                    } for usage in item.raw_material_usages.all()]
                }
                shipment_data['items'].append(item_data)
            
            shipment_history.append(shipment_data)

        return JsonResponse({
            'status': 'success',
            'data': {
                'statistics': statistics,
                'top_by_quantity': top_by_quantity,
                'top_by_revenue': top_by_revenue,
                'monthly_dynamics': monthly_dynamics,
                'shipment_history': shipment_history
            }
        })

    except Counterparty.DoesNotExist:
        raise NotFoundError("Контрагент не найден")
    except Exception as e:
        logger.error(f"Error in counterparty_details: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения детальной информации о контрагенте")

@api_view(['GET'])
def counterparty_groups_analysis(request):
    """API endpoint для анализа групп контрагентов"""
    try:
        # Получаем параметры из запроса
        period_months = int(request.GET.get('period_months', 12))
        end_date = request.GET.get('end_date')

        if end_date:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = timezone.now().date()
            
        start_date = end_date - timedelta(days=period_months * 30)
        
        # Создаем категоризатор и передаем даты
        categorizer = CounterpartyCategorizator(start_date=start_date, end_date=end_date)
        stats_df = categorizer.calculate_statistics()
        
        # Получаем категории контрагентов
        categories = categorizer.categorize()
        
        # Форматируем данные о границах категорий
        thresholds = {
            'monthly_volume': {
                'medium': float(categorizer.thresholds['monthly_volume']['medium']),
                'large': float(categorizer.thresholds['monthly_volume']['large'])
            },
            'frequency': {
                'rare': float(categorizer.thresholds['frequency']['rare']),
                'regular': float(categorizer.thresholds['frequency']['regular'])
            }
        }
        
        # Форматируем данные по каждой категории
        categories_data = {}
        for category, counterparties in categories.items():
            categories_data[category] = {
                'name': categorizer.CATEGORIES[category],
                'counterparties_count': len(counterparties),
                'total_monthly_volume': sum(c['avg_monthly'] for c in counterparties),
                'avg_frequency': sum(c['frequency'] for c in counterparties) / len(counterparties) if counterparties else 0,
                'counterparties': [{
                    'id': c['id'],
                    'name': c['name'],
                    'avg_monthly': float(c['avg_monthly']),
                    'frequency': float(c['frequency']),
                    'total_months': c['total_months'],
                    'total_sum': float(c['total_sum'])
                } for c in counterparties[:10]]  # Топ-10 контрагентов в каждой категории
            }
        
        return Response({
            'status': 'success',
            'data': {
                'thresholds': thresholds,
                'categories': categories_data,
                'total_counterparties': len(stats_df)
            }
        })
        
    except Exception as e:
        logger.error(f"Error in counterparty_groups_analysis: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка анализа групп контрагентов")

@api_view(['GET'])

def counterparty_group_details(request, category):
    """API endpoint для получения детальной информации о группе контрагентов"""
    try:
        if category not in CounterpartyCategorizator.CATEGORIES:
            raise ValidationError("Неверная категория")
        
        # Получаем параметры периода
        end_date = request.GET.get('end_date')
        period_months = int(request.GET.get('period_months', 12))
        
        if end_date:
            end_date = timezone.datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            end_date = timezone.now().date()
            
        start_date = end_date - timedelta(days=period_months * 30)
        
        # Создаем категоризатор и получаем данные группы
        categorizer = CounterpartyCategorizator()
        categories = categorizer.categorize()
        
        if category not in categories:
            raise NotFoundError("Нет данных для этой категории")
            
        group_counterparties = categories[category]
        
        # Получаем детальную статистику по группе
        counterparties_data = []
        monthly_dynamics = {}
        
        # Помесячная динамика — одним запросом на всю группу. Прежде он шёл
        # на каждого контрагента, а суммы всё равно складывались в общий
        # помесячный итог: группировка по месяцу сразу по всем даёт то же
        # самое, но не растёт вместе с размером группы.
        monthly_rows = ShipmentItem.objects.filter(
            shipment__counterparty_id__in=[c['id'] for c in group_counterparties],
            shipment__date__range=(start_date, end_date)
        ).values(
            'shipment__date__year',
            'shipment__date__month'
        ).annotate(
            monthly_sum=Sum(F('price') * F('quantity'))
        ).order_by('shipment__date__year', 'shipment__date__month')

        for row in monthly_rows:
            month_key = f"{row['shipment__date__year']}-{row['shipment__date__month']:02d}"
            monthly_dynamics[month_key] = (
                monthly_dynamics.get(month_key, 0) + float(row['monthly_sum'])
            )

        for c in group_counterparties:
            counterparties_data.append({
                'id': c['id'],
                'name': c['name'],
                'avg_monthly': float(c['avg_monthly']),
                'frequency': float(c['frequency']),
                'total_months': int(c.get('total_months', 0)),
                'total_sum': float(c.get('total_sum', 0))
            })
        
        # Формируем помесячную динамику
        monthly_series = [
            {
                'month': month,
                'value': float(value)
            }
            for month, value in sorted(monthly_dynamics.items())
        ]
        
        return Response({
            'status': 'success',
            'data': {
                'category_name': categorizer.CATEGORIES[category],
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'months': period_months
                },
                'statistics': {
                    'counterparties_count': len(counterparties_data),
                    'total_volume': sum(c['total_sum'] for c in counterparties_data),
                    'avg_frequency': sum(c['frequency'] for c in counterparties_data) / len(counterparties_data) if counterparties_data else 0
                },
                'counterparties': counterparties_data,
                'monthly_dynamics': monthly_series
            }
        })
        
    except Exception as e:
        logger.error(f"Error in counterparty_group_details: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения деталей группы контрагентов")
