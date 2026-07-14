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
    RawMaterialUsage,
    SupplyItem,
    Supply
)
from forecasting.services.analysis.optimized_purchase_analyzer import OptimizedPurchaseAnalyzer
from api.exceptions import APIException, NotFoundError, DataProcessingError, ValidationError
from api.utils import to_float_safe as safe_float, get_period_dates

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
       period_months = material.lead_time_period_months or 12
       period_is_custom = material.lead_time_period_months is not None

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
       general_calculator = PurchaseOptimizationCalculator(all_orders, material_id)
       general_calculations = general_calculator.get_full_recommendations()

       # Получаем оптимизацию и рекомендации для каждого поставщика
       try:
           optimization = analyzer.get_purchase_optimization(material_id)
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

       # Для каждого поставщика делаем отдельные расчеты
       for recommendation in recommendations:
           supplier_name = recommendation['supplier_name']
           supplier_orders = [order for order in all_orders if order.supplier_name == supplier_name]
           
           if supplier_orders:
               try:
                   calculator = PurchaseOptimizationCalculator(supplier_orders, material_id)
                   recommendation['detailed_calculations'] = calculator.get_full_recommendations()
               except Exception as e:
                   logger.error(f"Error calculating details for supplier {supplier_name}: {str(e)}")
                   recommendation['detailed_calculations'] = general_calculations
           else:
               recommendation['detailed_calculations'] = general_calculations

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

@api_view(['GET'])
def related_materials_analysis(request, material_id):
    """
    API endpoint для получения анализа связанных материалов.
    """
    try:
        # Проверяем существование материала
        try:
            material = RawMaterial.objects.get(id=material_id)
        except RawMaterial.DoesNotExist:
            raise NotFoundError("Материал не найден")

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
        
        # Создаем анализатор
        analyzer = OptimizedPurchaseAnalyzer(start_date, end_date)
        
        # Получаем анализ связанных материалов
        related_analysis = analyzer.find_related_materials(material_id)
        
        if 'error' in related_analysis:
            return Response({
                'status': 'error',
                'message': related_analysis['error']
            }, status=status.HTTP_400_BAD_REQUEST)

        # Добавляем безопасную обработку значений
        supplier_materials = {}
        for supplier_name, data in related_analysis.get('supplier_materials', {}).items():
            related_items = data.get('related', [])
            skipped_items = data.get('skipped', [])
            
            # Очищаем значения от NaN и None
            cleaned_related = []
            for item in related_items:
                cleaned_item = {
                    'name': item.get('name', ''),
                    'code': item.get('code', ''),
                    'uom': item.get('uom', ''),
                    'joint_count': safe_float(item.get('joint_count')),
                    'frequency': safe_float(item.get('frequency'))
                }
                cleaned_related.append(cleaned_item)

            cleaned_skipped = []
            for item in skipped_items:
                cleaned_item = {
                    'name': item.get('name', ''),
                    'code': item.get('code', ''),
                    'uom': item.get('uom', ''),
                    'joint_count': safe_float(item.get('joint_count')),
                    'frequency': safe_float(item.get('frequency')),
                    'skip_reason': item.get('skip_reason', '')
                }
                cleaned_skipped.append(cleaned_item)

            supplier_materials[supplier_name] = {
                'related': cleaned_related,
                'skipped': cleaned_skipped,
                'total_orders': data.get('total_orders', 0)
            }

        return Response({
            'status': 'success',
            'data': {
                'material_id': material_id,
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'months': period_months
                },
                'total_orders': related_analysis.get('total_orders', 0),
                'supplier_materials': supplier_materials
            }
        })

    except APIException:
        raise  # Re-raise API exceptions (NotFoundError, etc.)
    except Exception as e:
        logger.error(f"Error in related_materials_analysis: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка анализа связанных материалов")

@api_view(['PATCH'])
def update_material_period(request, material_id):
    """Обновить период расчёта времени доставки для материала"""
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

        material.lead_time_period_months = period_months
        material.save(update_fields=['lead_time_period_months'])

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


@api_view(['GET'])
def optimize_purchase_points(request, material_id):
    """
    API endpoint для получения оптимизированных точек заказа материала.
    """
    try:
        # Получаем параметры
        end_date = request.GET.get('end_date')
        period_months = int(request.GET.get('period_months', 12))
        safety_stock_days = int(request.GET.get('safety_stock_days', 14))
        
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d')
                end_date = timezone.make_aware(end_date)
            except ValueError:
                end_date = timezone.now()
        else:
            end_date = timezone.now()
            
        start_date = end_date - timedelta(days=period_months * 30)
        
        # Создаем анализатор
        analyzer = OptimizedPurchaseAnalyzer(start_date, end_date)
        
        try:
            material = RawMaterial.objects.get(id=material_id)
        except RawMaterial.DoesNotExist:
            raise NotFoundError("Материал не найден")

        # Получаем полную оптимизацию закупок
        optimization = analyzer.get_purchase_optimization(material_id)
        
        # Получаем историю использования для расчета средних значений
        usage_data = RawMaterialUsage.objects.filter(
            raw_material_id=material_id,
            shipment_item__shipment__date__range=(start_date, end_date)
        ).aggregate(
            total_usage=Sum('quantity'),
            total_days=Count('shipment_item__shipment__date', distinct=True)
        )

        total_usage = float(usage_data['total_usage'] or 0)
        total_days = usage_data['total_days'] or 1  # Избегаем деления на ноль
        
        # Рассчитываем среднее дневное использование
        avg_daily_usage = total_usage / total_days

        # Формируем рекомендации для каждого поставщика
        recommendations = []
        for supplier_id in optimization.get('recommendations', []):
            safety_stock = avg_daily_usage * safety_stock_days
            reorder_point = safety_stock * 2  # Условно берем двойной запас как точку заказа
            optimal_batch = max(reorder_point, 10)  # Минимальная партия 10 единиц

            recommendations.append({
                'supplier_name': supplier_id.get('supplier_name', ''),
                'reorder_point': safe_float(reorder_point),
                'optimal_batch': safe_float(optimal_batch),
                'safety_stock': safe_float(safety_stock),
                'lead_time': safe_float(supplier_id.get('lead_time', 5)),
                'reliability': safe_float(supplier_id.get('reliability', 1.0))
            })

        # Получаем связанные материалы
        related_materials = analyzer.find_related_materials(material_id)

        return Response({
            'status': 'success',
            'data': {
                'material': {
                    'id': material.id,
                    'name': material.name,
                    'code': material.code or '',
                    'group': material.group,
                    'uom': material.uom_name
                },
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'months': period_months
                },
                'parameters': {
                    'safety_stock_days': safety_stock_days
                },
                'usage_statistics': {
                    'total_usage': total_usage,
                    'avg_daily': safe_float(avg_daily_usage),
                    'avg_monthly': safe_float(avg_daily_usage * 30)
                },
                'recommendations': recommendations,
                'related_materials': related_materials
            }
        })

    except APIException:
        raise  # Re-raise API exceptions (NotFoundError, etc.)
    except Exception as e:
        logger.error(f"Error in optimize_purchase_points: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка оптимизации точек закупки")

