from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, F, Sum, Count, Max, DecimalField
from django.db.models.functions import TruncMonth, Coalesce 
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

import logging
logger = logging.getLogger(__name__)

@api_view(['GET'])
def counterparty_data(request):
    """API endpoint для получения данных по контрагентам с фильтрацией и пагинацией"""
    try:
        # Получаем параметры фильтрации
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('pageSize', 10))
        search = request.GET.get('search', '').strip()
        start_date = request.GET.get('startDate')
        end_date = request.GET.get('endDate')
        sort_field = request.GET.get('sortField', 'total_sales')
        sort_order = request.GET.get('sortOrder', 'desc')

        # Базовый QuerySet для отгрузок с фильтрацией по датам
        shipments_query = Shipment.objects.all()
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d')
                start_date = timezone.make_aware(start_date, timezone.get_current_timezone())
                shipments_query = shipments_query.filter(date__gte=start_date)
            except ValueError:
                pass

        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)
                end_date = timezone.make_aware(end_date, timezone.get_current_timezone())
                shipments_query = shipments_query.filter(date__lte=end_date)
            except ValueError:
                pass

        # Получаем ID контрагентов с отгрузками за период
        counterparty_ids = shipments_query.values_list('counterparty_id', flat=True).distinct()

        # Базовый QuerySet для контрагентов
        counterparties_query = Counterparty.objects.filter(id__in=counterparty_ids).annotate(
            shipments_count=Count(
                'shipment',
                filter=Q(shipment__in=shipments_query),
                distinct=True
            ),
            total_sales=Coalesce(
                Sum(
                    F('shipment__items__quantity') * F('shipment__items__price'),
                    filter=Q(shipment__in=shipments_query),
                    output_field=DecimalField()
                ),
                0,
                output_field=DecimalField()
            ),
            total_products=Count(
                'shipment__items__product',
                filter=Q(shipment__in=shipments_query),
                distinct=True
            ),
            last_shipment=Max('shipment__date', filter=Q(shipment__in=shipments_query))
        )

        # Улучшенный поиск по нескольким словам
        if search:
            search_words = search.split()
            search_query = Q()
            for word in search_words:
                word_query = Q(name__iregex=f'(?i){word}')
                search_query &= word_query
            counterparties_query = counterparties_query.filter(search_query)

        # Получаем отфильтрованные отгрузки для найденных контрагентов
        filtered_shipments = shipments_query.filter(
            counterparty__in=counterparties_query
        )

        # Получаем отфильтрованные товары
        filtered_items = ShipmentItem.objects.filter(
            shipment__in=filtered_shipments
        )

        # Обновляем статистику с учетом всех фильтров
        stats = {
            'total_counterparties': counterparties_query.count(),
            'total_shipments': filtered_shipments.count(),
            'total_products': filtered_items.values('product').distinct().count()
        }

        # Применяем сортировку
        if sort_field == 'name':
            sort_prefix = '-' if sort_order == 'desc' else ''
            counterparties_query = counterparties_query.order_by(f'{sort_prefix}name')
        elif sort_field in ['total_sales', 'shipments_count', 'total_products', 'last_shipment']:
            sort_prefix = '-' if sort_order == 'desc' else ''
            counterparties_query = counterparties_query.order_by(f'{sort_prefix}{sort_field}')

        # Пагинация
        paginator = Paginator(counterparties_query, page_size)
        page_data = paginator.get_page(page)

        # Форматируем данные для ответа
        counterparties_data = []
        for c in page_data:
            counterparty_data = {
                'id': c.id,
                'name': c.name,
                'total_sales': float(c.total_sales),
                'shipments_count': c.shipments_count,
                'total_products': c.total_products,
                'last_shipment': c.last_shipment.isoformat() if c.last_shipment else None
            }
            counterparties_data.append(counterparty_data)

        return JsonResponse({
            'status': 'success',
            'data': {
                'counterparties': counterparties_data,
                'total': paginator.count,
                'stats': stats
            }
        })

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
        
        for c in group_counterparties:
            # Получаем помесячные данные для контрагента
            shipments = ShipmentItem.objects.filter(
                shipment__counterparty_id=c['id'],
                shipment__date__range=(start_date, end_date)
            ).values(
                'shipment__date__year',
                'shipment__date__month'
            ).annotate(
                monthly_sum=Sum(F('price') * F('quantity'))
            ).order_by('shipment__date__year', 'shipment__date__month')
            
            # Собираем статистику по месяцам
            for shipment in shipments:
                month_key = f"{shipment['shipment__date__year']}-{shipment['shipment__date__month']:02d}"
                if month_key not in monthly_dynamics:
                    monthly_dynamics[month_key] = 0
                monthly_dynamics[month_key] += float(shipment['monthly_sum'])
            
            # Собираем данные по контрагенту
            counterparty_data = {
                'id': c['id'],
                'name': c['name'],
                'avg_monthly': float(c['avg_monthly']),
                'frequency': float(c['frequency']),
                'total_months': int(c.get('total_months', 0)),  # Добавляем это поле
                'total_sum': float(c.get('total_sum', 0))      # Добавляем это поле
            }
            counterparties_data.append(counterparty_data)
        
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
