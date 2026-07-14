# forecasting/services/analysis/optimized_purchase_analyzer.py

from django.db.models import Avg, Sum, F, Count, Q
from django.db import models
import logging
from datetime import datetime, timedelta
from django.utils import timezone

from core.models import (
    PurchaseOrder, 
    PurchaseOrderItem,
    RawMaterial,
    Supply,
    SupplyItem
)
from forecasting.services.analysis.seasonal_demand_analyzer import SeasonalDemandAnalyzer

from forecasting.services.analysis.purchase_optimizer import (
    PurchaseOptimizationCalculator,
    OrderHistory,
    get_material_order_history
)

logger = logging.getLogger(__name__)

class OptimizedPurchaseAnalyzer:
    """
    Анализатор для оптимизации закупок:
    - История заказов по поставщикам 
    - Статистика сроков поставки
    - Размеры заказов
    - Связанные материалы
    """
    
    def __init__(self, start_date=None, end_date=None):
        """
        Если даты не указаны, анализируем все данные.
        Даты можно указать опционально для конкретного периода.
        """
        self.start_date = start_date
        self.end_date = end_date

    def analyze_supplier_performance(self, material_id, months=12):
        """Анализ статистики поставщиков

        Args:
            material_id: ID материала
            months: количество месяцев для анализа (по умолчанию 12)
        """
        try:
            # Определяем период для фильтрации
            end_date = timezone.now()
            start_date = end_date - timedelta(days=months * 30)

            # Получаем все заказы с материалом за период
            purchase_orders = PurchaseOrder.objects.filter(
                items__raw_material_id=material_id,
                date__gte=start_date,
                date__lte=end_date
            ).select_related(
                'counterparty'
            ).prefetch_related('items').distinct()

            # Получаем все приемки с материалом для быстрого поиска за период
            supplies = Supply.objects.filter(
                items__raw_material_id=material_id,
                date__gte=start_date,
                date__lte=end_date
            ).select_related(
                'counterparty'
            ).order_by('date')

            suppliers_stats = {}
            recent_date = timezone.now() - timedelta(days=60)  # Заказы за последние 60 дней
            
            for order in purchase_orders:
                supplier_id = order.counterparty.id
                
                if supplier_id not in suppliers_stats:
                    suppliers_stats[supplier_id] = {
                        'supplier_name': order.counterparty.name,
                        'total_orders': 0,
                        'completed_orders': 0,
                        'orders_in_transit': 0,
                        'avg_lead_time': 0,
                        'min_lead_time': float('inf'),
                        'max_lead_time': 0,
                        'common_quantities': {},
                        'orders': []
                    }

                stats = suppliers_stats[supplier_id]
                stats['total_orders'] += 1

                # Определяем является ли заказ "в пути"
                is_in_transit = False
                if order.date >= recent_date and not order.supplies.exists():
                    is_in_transit = True
                    stats['orders_in_transit'] += 1

                # Ищем ближайшую приемку после даты заказа
                matching_supply = supplies.filter(
                    counterparty=order.counterparty,
                    date__gt=order.date
                ).first()

                lead_time = 0
                if matching_supply:
                    stats['completed_orders'] += 1
                    lead_time = (matching_supply.date - order.date).days
                    
                    # Обновляем статистику по срокам только для завершенных заказов
                    if stats['min_lead_time'] == float('inf'):
                        stats['min_lead_time'] = lead_time
                    else:
                        stats['min_lead_time'] = min(stats['min_lead_time'], lead_time)
                    stats['max_lead_time'] = max(stats['max_lead_time'], lead_time)
                    
                    if stats['completed_orders'] > 0:
                        prev_total = stats['avg_lead_time'] * (stats['completed_orders'] - 1)
                        stats['avg_lead_time'] = (prev_total + lead_time) / stats['completed_orders']

                # Собираем информацию о размерах заказов
                for item in order.items.filter(raw_material_id=material_id):
                    quantity = float(item.quantity)
                    if quantity in stats['common_quantities']:
                        stats['common_quantities'][quantity] += 1
                    else:
                        stats['common_quantities'][quantity] = 1

                    order_info = {
                        'date': order.date.isoformat(),
                        'quantity': quantity,
                        'price': float(item.price),
                        'lead_time': lead_time,
                        'supplier_name': order.counterparty.name,
                        'is_in_transit': is_in_transit
                    }
                    
                    if matching_supply:
                        order_info['supply_number'] = matching_supply.number
                        order_info['supply_date'] = matching_supply.date.isoformat()

                    stats['orders'].append(order_info)

                # Считаем надежность без учета заказов в пути
                if stats['total_orders'] > 0:
                    stats['delivery_reliability'] = stats['completed_orders'] / stats['total_orders']
                else:
                    stats['delivery_reliability'] = 1.0

                # Сортируем заказы по дате
                stats['orders'].sort(key=lambda x: x['date'], reverse=True)

                # Очищаем специальные значения для поставщиков без завершенных поставок
                if stats['min_lead_time'] == float('inf'):
                    stats['min_lead_time'] = 0
                    stats['max_lead_time'] = 0
                    stats['avg_lead_time'] = 0

            return {
                'material_id': material_id,
                'suppliers': suppliers_stats
            }

        except Exception as e:
            logger.error(f"Error analyzing supplier performance: {str(e)}")
            return {'error': str(e)}
    
    def find_related_materials(self, material_id: int) -> dict:
        """Поиск материалов, которые часто заказываются вместе"""
        try:
            base_orders = PurchaseOrderItem.objects.filter(
                raw_material_id=material_id
            )

            if self.start_date and self.end_date:
                base_orders = base_orders.filter(
                    purchase_order__date__range=(self.start_date, self.end_date)
                )

            base_order_ids = base_orders.values_list('purchase_order_id', flat=True)
            total_orders = len(set(base_order_ids))

            if not total_orders:
                return {
                    'error': 'Нет данных о заказах',
                    'material_id': material_id
                }

            supplier_materials = {}
            
            # Словарь для агрегации данных по материалам
            material_aggregates = {}
            
            for order_id in base_order_ids:
                order = PurchaseOrder.objects.get(id=order_id)
                supplier = order.counterparty
                
                if supplier.name not in supplier_materials:
                    supplier_materials[supplier.name] = {
                        'related': [],
                        'skipped': [],
                        'total_orders': 0
                    }

                related_items = PurchaseOrderItem.objects.filter(
                    purchase_order_id=order_id
                ).exclude(
                    raw_material_id=material_id
                ).select_related('raw_material')

                for item in related_items:
                    material_key = f"{supplier.name}_{item.raw_material.id}"
                    
                    if material_key not in material_aggregates:
                        joint_orders = PurchaseOrderItem.objects.filter(
                            raw_material=item.raw_material,
                            purchase_order__counterparty=supplier
                        )
                        
                        if self.start_date and self.end_date:
                            joint_orders = joint_orders.filter(
                                purchase_order__date__range=(self.start_date, self.end_date)
                            )
                        
                        joint_orders_count = joint_orders.count()
                        frequency = (joint_orders_count / total_orders) * 100

                        # Вычисляем среднее количество
                        total_quantity = sum(float(jo.quantity) for jo in joint_orders)
                        avg_quantity = total_quantity / joint_orders_count if joint_orders_count > 0 else 0

                        material_aggregates[material_key] = {
                            'name': item.raw_material.name,
                            'code': item.raw_material.code,
                            'uom': item.raw_material.uom_name,
                            'frequency': frequency,
                            'total_joint_orders': joint_orders_count,
                            'avg_quantity': avg_quantity
                        }

                supplier_materials[supplier.name]['total_orders'] += 1

            # Распределяем агрегированные данные по поставщикам
            for material_key, material_info in material_aggregates.items():
                supplier_name = material_key.split('_')[0]
                if material_info['frequency'] >= 5:
                    if material_info not in supplier_materials[supplier_name]['related']:
                        supplier_materials[supplier_name]['related'].append(material_info)
                else:
                    material_info['skip_reason'] = f'частота заказов {material_info["frequency"]:.1f}% < 5%'
                    if material_info not in supplier_materials[supplier_name]['skipped']:
                        supplier_materials[supplier_name]['skipped'].append(material_info)

            return {
                'material_id': material_id,
                'total_orders': total_orders,
                'supplier_materials': supplier_materials
            }

        except Exception as e:
            logger.error(f"Error finding related materials for {material_id}: {str(e)}")
            return {'error': str(e)}
        
    def analyze_seasonality(self, material_id) -> dict:
        """Анализ сезонности для материала"""
        try:
            seasonal_analyzer = SeasonalDemandAnalyzer(
                start_date=timezone.now() - timedelta(days=365),
                end_date=timezone.now()
            )
            
            seasonal_data = seasonal_analyzer.analyze_seasonality_pattern(
                seasonal_analyzer.get_sales_history(material_id)
            )
            
            # Проверяем наличие ошибки в ответе
            if 'error' in seasonal_data:
                return {
                    "type": "NO_SEASONALITY",
                    "current_factor": 1.0,
                    "recommendation": seasonal_data['error']
                }
            
            # Если нет seasonal_factors, это нормальная ситуация для материалов без сезонности    
            if 'seasonal_factors' not in seasonal_data:
                return {
                    "type": "NO_SEASONALITY",
                    "current_factor": 1.0,
                    "recommendation": "Сезонность не выявлена"
                }
                
            current_month = timezone.now().month
            seasonal_factor = seasonal_data['seasonal_factors'].get(current_month, 1.0)
            
            return {
                "type": seasonal_data.get('seasonality_type', 'NO_SEASONALITY'),
                "current_factor": seasonal_factor,
                "recommendation": f"""
                Сезонность: {seasonal_data.get('seasonality_type', 'Не выявлена')}
                Текущий сезонный коэффициент: {seasonal_factor:.2f}
                {'Рекомендуется увеличить заказ' if seasonal_factor > 1.1 else 'Рекомендуется стандартный заказ'}
                """
            }
        except Exception as e:
            logger.error(f"Error in analyze_seasonality: {str(e)}")
            return {
                "type": "NO_SEASONALITY",
                "current_factor": 1.0,
                "recommendation": "Не удалось проанализировать сезонность"
            }
    
    
    def get_purchase_optimization(self, material_id: int) -> dict:
        try:
            material = RawMaterial.objects.get(id=material_id)
            
            # Анализ поставщиков
            supplier_analysis = self.analyze_supplier_performance(material_id)
            if 'error' in supplier_analysis:
                return supplier_analysis

            recommendations = []
            
            for supplier_id, stats in supplier_analysis['suppliers'].items():
                # Получаем заказы только для текущего поставщика
                supplier_orders = get_material_order_history(material_id)
                supplier_orders = [
                    order for order in supplier_orders 
                    if order.supplier_name == stats['supplier_name']
                ]
                
                if not supplier_orders:
                    continue

                # Используем PurchaseOptimizationCalculator для расчетов
                calculator = PurchaseOptimizationCalculator(supplier_orders, material_id)
                detailed_calcs = calculator.get_full_recommendations()

                # Берем все значения из калькулятора
                recommendations.append({
                    'supplier_name': stats['supplier_name'],
                    'reorder_point': detailed_calcs['reorder_point']['value'],
                    'optimal_batch': detailed_calcs['optimal_order_quantity']['value'],
                    'safety_stock': detailed_calcs['safety_stock']['value'],
                    'lead_time': stats['avg_lead_time'],
                    'reliability': stats['delivery_reliability'],
                    'detailed_calculations': detailed_calcs
                })

            return {
                'material': {
                    'id': material.id,
                    'name': material.name,
                    'code': material.code,
                    'uom': material.uom_name
                },
                'recommendations': recommendations
            }

        except RawMaterial.DoesNotExist:
            return {'error': f'Material {material_id} not found'}
        except Exception as e:
            logger.error(f"Error optimizing purchases for {material_id}: {str(e)}")
            return {'error': str(e)}
