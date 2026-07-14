# forecasting/services/analysis/component_demand_analyzer.py

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from django.db.models import Sum, F, Avg, Min, Max
from decimal import Decimal
from django.db import models
import logging
from datetime import datetime, timedelta
from django.utils import timezone

from core.models import (
    Product, 
    ShipmentItem, 
    ProcessingPlanProduct,
    ProcessingPlanMaterial,
    RawMaterial
)

logger = logging.getLogger(__name__)

class ComponentDemandAnalyzer:
    """
    Анализатор потребности в компонентах на основе продаж готовой продукции
    """
    
    def __init__(self, start_date=None, end_date=None, forecast_months: int = 12):
        self.start_date = start_date
        self.end_date = end_date
        self.forecast_months = forecast_months
        
    def get_product_components(self, product_id: int) -> List[Dict]:
        """
        Получение списка компонентов для продукта с их количеством из техкарты
        """
        try:
            components = []
            
            # Получаем самую последнюю техкарту
            plan_query = ProcessingPlanProduct.objects.filter(
                product_id=product_id
            ).select_related('processing_plan')
            
            plan = plan_query.first()
            
            if not plan:
                logger.warning(f"No processing plan found for product {product_id}")
                return components
                
            # Получаем материалы из техкарты
            materials_query = ProcessingPlanMaterial.objects.filter(
                processing_plan=plan.processing_plan
            ).select_related('material')
            
            materials = list(materials_query)
            
            for material in materials:
                components.append({
                    'material_id': material.material.id,
                    'name': material.material.name,
                    'quantity': float(material.quantity),
                    'uom': material.material.uom_name,
                    'code': material.material.code or 'Нет',  # Используем код вместо артикула
                    'min_order': 0
                })
            
            return components
                
        except Exception as e:
            logger.error(f"Error getting components for product {product_id}: {str(e)}")
            return []

    def get_historical_stats(self, product_id: int) -> Dict:
        """
        Получение статистики по историческим продажам
        """
        try:
            stats = ShipmentItem.objects.filter(
                product_id=product_id,
                shipment__date__range=(self.start_date, self.end_date)
            ).values('shipment__date__month').annotate(
                monthly_qty=Sum('quantity')
            ).aggregate(
                min_monthly=Min('monthly_qty'),
                max_monthly=Max('monthly_qty'),
                avg_monthly=Avg('monthly_qty')
            )
            
            # Преобразуем None в 0 если нет данных
            return {
                'min_monthly': float(stats['min_monthly'] or 0),
                'max_monthly': float(stats['max_monthly'] or 0),
                'avg_monthly': float(stats['avg_monthly'] or 0)
            }
            
        except Exception as e:
            logger.error(f"Error getting historical stats: {str(e)}")
            return {
                'min_monthly': 0,
                'max_monthly': 0,
                'avg_monthly': 0
            }

    def calculate_monthly_demand(self, product_id: int, sales_forecast: pd.Series, historical_stats: Dict) -> pd.DataFrame:
        """
        Расчет помесячной потребности в компонентах на основе прогноза продаж
        """
        try:
            components = self.get_product_components(product_id)
            if not components:
                return pd.DataFrame()
                
            demand_data = []
            
            for component in components:
                component_qty = component['quantity']
                
                # Для каждого компонента рассчитываем потребность
                for date, forecast_qty in sales_forecast.items():
                    # Расчет потребности на основе прогноза
                    forecast_demand = forecast_qty * component_qty
                    
                    # Расчет исторических значений
                    hist_max = historical_stats['max_monthly'] * component_qty
                    hist_min = historical_stats['min_monthly'] * component_qty
                    
                    demand_data.append({
                        'date': date,
                        'material_id': component['material_id'],
                        'material_name': component['name'],
                        'material_code': component['code'],
                        'quantity': forecast_demand,
                        'hist_max': hist_max,
                        'hist_min': hist_min,
                        'uom': component['uom'],
                        'min_order': component['min_order']
                    })
            
            return pd.DataFrame(demand_data)
            
        except Exception as e:
            logger.error(f"Error calculating monthly demand for product {product_id}: {str(e)}")
            return pd.DataFrame()

    def get_related_components(self, material_ids: List[int]) -> Dict[int, List[int]]:
        """
        Получение групп связанных компонентов (которые часто закупаются вместе)
        """
        try:
            related_groups = {}
            
            # Здесь будет логика определения связанных компонентов
            # Пока заглушка - каждый компонент сам по себе
            for material_id in material_ids:
                related_groups[material_id] = [material_id]
                
            return related_groups
            
        except Exception as e:
            logger.error(f"Error getting related components: {str(e)}")
            return {}

    def analyze_product_demand(self, 
                            product_id: int, 
                            sales_forecast: pd.Series,
                            lead_time_days: int = 30) -> Dict:
       """
       Полный анализ потребности в компонентах для продукта
       """
       try:
           # Получаем статистику по историческим продажам
           historical_stats = self.get_historical_stats(product_id)
           
           # Получаем базовую потребность в компонентах
           monthly_demand = self.calculate_monthly_demand(
               product_id, 
               sales_forecast,
               historical_stats
           )
           
           if monthly_demand.empty:
               return {
                   'error': 'Нет данных о компонентах продукта',
                   'product_id': product_id
               }

           # Агрегируем данные по материалам
           material_stats = monthly_demand.groupby('material_id').agg({
               'material_name': 'first',
               'material_code': 'first',
               'uom': 'first',
               'min_order': 'first',
               'quantity': ['mean', 'max'],
               'hist_max': 'first',
               'hist_min': 'first'
           }).reset_index()

           # Получаем связанные компоненты
           material_ids = [int(x) for x in material_stats['material_id'].tolist()]
           related_groups = self.get_related_components(material_ids)

           purchasing_recommendations = []

           # Используем to_dict('records') для ~100x ускорения вместо iterrows()
           for row in material_stats.to_dict('records'):
               material_id = int(row['material_id'])
               min_order = float(row[('min_order', 'first')])
               avg_monthly = float(row[('quantity', 'mean')])

               # Используем максимум из прогнозного и исторического максимума
               max_monthly = max(
                   float(row[('quantity', 'max')]),
                   float(row[('hist_max', 'first')])
               )

               # Используем минимум из исторического
               min_monthly = float(row[('hist_min', 'first')])

               # Расчет рекомендуемого объема закупки
               if min_order > 0:
                   recommended_qty = max(
                       min_order,
                       np.ceil(avg_monthly * (lead_time_days/30) / min_order) * min_order
                   )
               else:
                   safety_stock = avg_monthly * 0.5  # 50% от среднемесячной потребности
                   recommended_qty = avg_monthly + safety_stock

               purchasing_recommendations.append({
                   'material_id': material_id,
                   'material_name': row[('material_name', 'first')],
                   'material_code': row[('material_code', 'first')],
                   'uom': row[('uom', 'first')],
                   'min_order': min_order,
                   'avg_monthly_demand': avg_monthly,
                   'max_monthly_demand': max_monthly,
                   'min_monthly_demand': min_monthly,
                   'recommended_qty': recommended_qty,
                   'related_materials': related_groups.get(material_id, []),
                   'lead_time_days': lead_time_days
               })

           return {
               'product_id': product_id,
               'monthly_demand': monthly_demand,
               'recommendations': purchasing_recommendations,
               'historical_stats': historical_stats,
               'forecast_info': {
                   'monthly_forecast': float(sales_forecast.iloc[0]),
                   'months': len(sales_forecast)
               }
           }
           
       except Exception as e:
           logger.error(f"Error analyzing demand for product {product_id}: {str(e)}")
           logger.exception("Full traceback:")
           return {'error': str(e)}