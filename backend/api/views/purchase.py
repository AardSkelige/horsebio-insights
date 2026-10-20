from django.db.models.functions import TruncMonth
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Count, Sum, Avg, F

from core.models import (
    RawMaterial,
    PurchaseOrder,
    PurchaseOrderItem,
    SupplyItem,
    Supply
)
from api.models import MaterialPeriodPreference
from forecasting.services.analysis.optimized_purchase_analyzer import OptimizedPurchaseAnalyzer
from api.exceptions import APIException, NotFoundError, DataProcessingError, ValidationError

import logging
logger = logging.getLogger(__name__)

@api_view(['GET'])
def purchase_analysis_overview(request):
    """
    API endpoint для получения общего анализа закупок.
    Возвращает:
    - Общую статистику по закупкам
    - Топ материалов по частоте закупок
    - Статистику по поставщикам
    - Анализ времени поставок
    """
    try:
        # Получаем параметры периода
        end_date = request.GET.get('end_date')
        period_months = int(request.GET.get('period_months', 12))
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
                end_date = timezone.make_aware(end_date)
            except ValueError:
                end_date = timezone.now()
        else:
            end_date = timezone.now()
            
        start_date = end_date - timedelta(days=period_months * 30)
        
        # Получаем базовые запросы
        purchase_orders = PurchaseOrder.objects.filter(
            date__range=(start_date, end_date)
        ).select_related('counterparty')
        
        order_items = PurchaseOrderItem.objects.filter(
            purchase_order__in=purchase_orders
        ).select_related('raw_material', 'purchase_order')

        # Основная статистика по закупкам
        total_stats = {
            'total_orders': purchase_orders.count(),
            'total_materials': order_items.values('raw_material').distinct().count(),
            'total_suppliers': purchase_orders.values('counterparty').distinct().count(),
            'total_sum': float(purchase_orders.aggregate(sum=Sum('sum'))['sum'] or 0),
            'avg_order_sum': float(
                purchase_orders.aggregate(avg=Avg('sum'))['avg'] or 0
            ),
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'months': period_months
            }
        }

        # Анализ времени поставок - вычисляем вручную
        lead_times = []
        for order in purchase_orders:
            lt = order.lead_time  # Используем property
            if lt is not None:
                lead_times.append(lt)

        if lead_times:
            lead_time_stats = {
                'min': min(lead_times),
                'max': max(lead_times),
                'avg': sum(lead_times) / len(lead_times),
                'median': sorted(lead_times)[len(lead_times) // 2]
            }
        else:
            lead_time_stats = {
                'min': 0,
                'max': 0,
                'avg': 0,
                'median': 0
            }

        # Топ материалов по количеству заказов
        top_materials = (
            order_items
            .values('raw_material__id', 'raw_material__name', 'raw_material__code')
            .annotate(
                orders_count=Count('purchase_order', distinct=True),
                total_quantity=Sum('quantity'),
                total_sum=Sum(F('quantity') * F('price')),
                avg_price=Avg('price')
            )
            .order_by('-orders_count')[:10]
        )

        # Статистика по поставщикам
        suppliers_stats = (
            purchase_orders
            .values('counterparty__id', 'counterparty__name')
            .annotate(
                orders_count=Count('id'),
                total_sum=Sum('sum'),
                materials_count=Count('items__raw_material', distinct=True)
            )
            .order_by('-orders_count')[:10]
        )

        # Анализ регулярности закупок
        monthly_orders = (
            purchase_orders
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(
                orders_count=Count('id'),
                total_sum=Sum('sum'),
                materials_count=Count('items__raw_material', distinct=True)
            )
            .order_by('month')
        )

        return Response({
            'status': 'success',
            'data': {
                'total_statistics': total_stats,
                'lead_time_analysis': lead_time_stats,
                'top_materials': [{
                    'id': m['raw_material__id'],
                    'name': m['raw_material__name'],
                    'code': m['raw_material__code'] or '-',
                    'orders_count': m['orders_count'],
                    'total_quantity': float(m['total_quantity']),
                    'total_sum': float(m['total_sum']),
                    'avg_price': float(m['avg_price'] or 0)
                } for m in top_materials],
                'top_suppliers': [{
                    'id': s['counterparty__id'],
                    'name': s['counterparty__name'],
                    'orders_count': s['orders_count'],
                    'total_sum': float(s['total_sum']),
                    'materials_count': s['materials_count']
                } for s in suppliers_stats],
                'monthly_dynamics': [{
                    'month': item['month'].isoformat(),
                    'orders_count': item['orders_count'],
                    'total_sum': float(item['total_sum']),
                    'materials_count': item['materials_count']
                } for item in monthly_orders]
            }
        })

    except Exception as e:
        logger.error(f"Error in purchase_analysis_overview: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения анализа закупок")

from datetime import datetime as dt
from forecasting.services.analysis.purchase_optimizer import (
    PurchaseOptimizationCalculator,
    get_material_order_history
)
@api_view(['GET'])
def material_purchase_analysis(request, material_id):
   try:
       try:
           material = RawMaterial.objects.get(id=material_id)
       except RawMaterial.DoesNotExist:
           raise NotFoundError("Материал не найден")

       # Получить период для материала (или 12 по умолчанию)
       preference = MaterialPeriodPreference.objects.filter(user=request.user, raw_material=material).first()
       period_months = preference.period_months if preference else 12
       period_is_custom = preference is not None

       # Создаем анализатор и получаем статистику поставщиков
       analyzer = OptimizedPurchaseAnalyzer()
       supplier_analysis = analyzer.analyze_supplier_performance(material_id, months=period_months)

       if 'error' in supplier_analysis:
           return Response({
               'status': 'error',
               'message': supplier_analysis['error']
           }, status=400)

       suppliers_stats = supplier_analysis['suppliers']

       # Получаем все заказы для общего расчета с учётом периода
       all_orders = get_material_order_history(material_id, months=period_months)
       orders_count = len(all_orders)

       # Делаем общий расчет без учета поставщиков
       general_calculator = PurchaseOptimizationCalculator(all_orders, material_id, consumption_months=period_months)
       general_calculations = general_calculator.get_full_recommendations()

       # Получаем оптимизацию и рекомендации для каждого поставщика
       try:
           optimization = analyzer.get_purchase_optimization(material_id, months=period_months)
           if 'error' in optimization:
               return Response({
                   'status': 'error',
                   'message': optimization['error']
               }, status=400)
       except Exception as e:
           logger.error(f"Error in optimization: {str(e)}")
           optimization = {
               'recommendations': [],
               'material': {
                   'id': material.id,
                   'name': material.name,
                   'code': material.code,
                   'uom': material.uom_name
               }
           }

       recommendations = optimization.get('recommendations', [])

       # Получаем связанные материалы
       related_materials = analyzer.find_related_materials(material_id)

       return Response({
           'status': 'success',
           'data': {
               'material': {
                   'id': material.id,
                   'name': material.name,
                   'code': material.code,
                   'uom': material.uom_name
               },
               'period_months': period_months,
               'period_is_custom': period_is_custom,
               'orders_count': orders_count,
               'general_calculations': general_calculations,
               'suppliers': suppliers_stats,
               'recommendations': recommendations,
               'related_materials': related_materials
           }
       })

   except APIException:
       raise  # Re-raise API exceptions (NotFoundError, etc.)
   except Exception as e:
       logger.error(f"Error in material_purchase_analysis: {str(e)}", exc_info=True)
       raise DataProcessingError("Ошибка анализа закупок материала")

@api_view(['PATCH'])
def update_material_period(request, material_id):
    """Сохранить личный период расчёта закупок по материалу"""
    try:
        try:
            material = RawMaterial.objects.get(id=material_id)
        except RawMaterial.DoesNotExist:
            raise NotFoundError("Материал не найден")

        period_months = request.data.get('period_months')  # None = сбросить к умолчанию

        # Валидация: если значение указано, оно должно быть положительным целым числом
        if period_months is not None:
            try:
                period_months = int(period_months)
                if period_months <= 0 or period_months > 24:
                    raise ValidationError("Период должен быть от 1 до 24 месяцев")
            except (ValueError, TypeError):
                raise ValidationError("Период должен быть целым числом")

        if period_months is None:
            MaterialPeriodPreference.objects.filter(user=request.user, raw_material=material).delete()
        else:
            MaterialPeriodPreference.objects.update_or_create(
                user=request.user, raw_material=material, defaults={'period_months': period_months}
            )

        return Response({
            'status': 'success',
            'data': {
                'material_id': material.id,
                'period_months': period_months or 12,
                'period_is_custom': period_months is not None
            }
        })

    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error in update_material_period: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка обновления периода материала")

