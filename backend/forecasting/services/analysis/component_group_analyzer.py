# forecasting/services/analysis/component_group_analyzer.py

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from django.db.models import Sum, F, Avg, Count
from django.db import models
from decimal import Decimal
import logging

from core.models import (
    Product,
    ProcessingPlanProduct,
    ProcessingPlanMaterial,
    RawMaterial
)

from .seasonal_demand_analyzer import SeasonalDemandAnalyzer

logger = logging.getLogger(__name__)

class ComponentGroupAnalyzer:
    """
    Анализатор для группировки потребностей в компонентах по всем продуктам
    """
    
    def __init__(self, start_date=None, end_date=None):
        self.start_date = start_date
        self.end_date = end_date
        self.seasonal_analyzer = SeasonalDemandAnalyzer(start_date, end_date)
        
    def get_product_components_with_seasonality(self, product_id: int) -> Dict:
        """
        Получает компоненты продукта с учетом сезонности продаж
        """
        try:
            # Получаем техкарту
            plan = ProcessingPlanProduct.objects.filter(
                product_id=product_id
            ).select_related('processing_plan').first()
            
            if not plan:
                return {
                    'error': f'Техкарта не найдена для продукта {product_id}'
                }
            
            # Получаем историю продаж и анализ сезонности
            sales_history = self.seasonal_analyzer.get_sales_history(product_id)
            
            # Если нет данных о продажах, используем равномерное распределение
            if sales_history.empty:
                logger.warning(f"Нет данных о продажах для продукта {product_id}, используем равномерное распределение")
                seasonal_factors = {month: 1.0 for month in range(1, 13)}
                avg_monthly_sales = 0  # или можно установить какое-то дефолтное значение
                seasonality_type = 'NO_DATA'
            else:
                seasonality = self.seasonal_analyzer.analyze_seasonality_pattern(sales_history)
                seasonal_factors = seasonality['seasonal_factors']
                avg_monthly_sales = float(sales_history.mean())
                seasonality_type = seasonality['seasonality_type']
                
            # Получаем компоненты
            components = []
            materials = ProcessingPlanMaterial.objects.filter(
                processing_plan=plan.processing_plan
            ).select_related('material')
            
            for material in materials:
                # Для каждого компонента рассчитываем потребность с учетом сезонности
                monthly_requirements = {}
                for month in range(1, 13):
                    factor = seasonal_factors.get(month, 1.0)
                    required_qty = avg_monthly_sales * float(material.quantity) * factor
                    
                    monthly_requirements[month] = {
                        'base_qty': float(material.quantity),
                        'sales_forecast': avg_monthly_sales,
                        'seasonal_factor': factor,
                        'required_qty': required_qty
                    }
                
                components.append({
                    'material_id': material.material.id,
                    'material_name': material.material.name,
                    'material_code': material.material.code,
                    'unit': material.material.uom_name,
                    'base_qty': float(material.quantity),
                    'monthly_requirements': monthly_requirements
                })
            
            return {
                'product_id': product_id,
                'seasonality_type': seasonality_type,
                'components': components,
                'has_sales_data': not sales_history.empty
            }
            
        except Exception as e:
            logger.error(f"Error analyzing product components: {str(e)}")
            logger.exception("Full traceback:")
            return {'error': str(e)}
        
    def aggregate_components_demand(self) -> Dict:
        """
        Агрегирует потребности в компонентах по всем продуктам
        """
        try:
            # Получаем все продукты с техкартами и продажами
            products = Product.objects.filter(
                processingplanproduct__isnull=False,
                shipmentitem__isnull=False
            ).annotate(
                sales_count=Count('shipmentitem')
            ).filter(
                sales_count__gt=0
            )
            
            # Словарь для хранения агрегированных потребностей
            aggregated_demand = {}
            
            # Для каждого продукта
            for product in products:
                result = self.get_product_components_with_seasonality(product.id)
                
                if 'error' in result or not result.get('components'):
                    continue
                    
                # Для каждого компонента продукта
                for component in result['components']:
                    material_id = component['material_id']
                    
                    # Создаем запись для компонента если её еще нет
                    if material_id not in aggregated_demand:
                        aggregated_demand[material_id] = {
                            'material_id': material_id,
                            'name': component['material_name'],
                            'code': component['material_code'],
                            'unit': component['unit'],
                            'monthly_demand': {month: 0 for month in range(1, 13)},
                            'products_using': [],
                        }
                    
                    # Добавляем продукт в список использующих этот компонент
                    aggregated_demand[material_id]['products_using'].append({
                        'product_id': product.id,
                        'product_name': product.name,
                        'base_qty': component['base_qty']
                    })
                    
                    # Суммируем потребности по месяцам
                    for month, req in component['monthly_requirements'].items():
                        aggregated_demand[material_id]['monthly_demand'][month] += req['required_qty']
            
            # Рассчитываем статистику для каждого компонента
            for material_id, data in aggregated_demand.items():
                monthly_values = list(data['monthly_demand'].values())
                data['statistics'] = {
                    'total_annual': sum(monthly_values),
                    'avg_monthly': sum(monthly_values) / 12,
                    'max_monthly': max(monthly_values),
                    'min_monthly': min(monthly_values),
                    'peak_month': max(data['monthly_demand'].items(), key=lambda x: x[1])[0],
                    'min_month': min(data['monthly_demand'].items(), key=lambda x: x[1])[0],
                    'products_count': len(data['products_using'])
                }
            
            return {
                'components': aggregated_demand,
                'total_components': len(aggregated_demand),
                'total_products': len(products),
                'period': {
                    'start_date': self.start_date,
                    'end_date': self.end_date
                }
            }
            
        except Exception as e:
            logger.error(f"Error aggregating components demand: {str(e)}")
            logger.exception("Full traceback:")
            return {'error': str(e)}