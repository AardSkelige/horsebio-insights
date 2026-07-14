# forecasting/services/analysis/abc_analyzer.py

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from django.db.models import Sum, F, Count, Avg
from django.db import models
from decimal import Decimal
from core.models import ShipmentItem, Product, Shipment
import logging

logger = logging.getLogger(__name__)


def safe_float(value, default=0.0):
    """
    Safely convert value to float, handling NaN and None.
    """
    if value is None:
        return default
    try:
        float_value = float(value)
        if pd.isna(float_value) or np.isnan(float_value):
            return default
        return float_value
    except (ValueError, TypeError):
        return default

class ABCAnalyzer:
    """
    Класс для проведения ABC-анализа продуктов на основе продаж
    """
    
    def __init__(self, start_date=None, end_date=None):
        self.start_date = start_date
        self.end_date = end_date
        self.a_threshold = Decimal('0.8')  # Группа A: 0-80% выручки
        self.b_threshold = Decimal('0.95') # Группа B: 80-95% выручки
        # Группа C: 95-100% выручки
    
    def get_product_sales(self) -> pd.DataFrame:
        """
        Получение расширенных данных о продажах по каждому продукту
        Включает информацию о частоте продаж, средних продажах в месяц и т.д.
        """
        try:
            # Базовый запрос продаж с дополнительными метриками
            query = ShipmentItem.objects.values(
                'product__id',
                'product__name',
                'product__article',
                'product__group',
                'product__subgroup'
            ).annotate(
                total_revenue=Sum(F('price') * F('quantity'), output_field=models.DecimalField()),
                total_quantity=Sum('quantity'),
                avg_price=Avg('price'),
                orders_count=Count('shipment', distinct=True)
            )
            
            # Добавляем фильтры по датам
            if self.start_date:
                query = query.filter(shipment__date__gte=self.start_date)
            if self.end_date:
                query = query.filter(shipment__date__lte=self.end_date)
                
            # Получаем общее количество месяцев в периоде
            months_count = 12  # По умолчанию год
            if self.start_date and self.end_date:
                months_count = (
                    (self.end_date.year - self.start_date.year) * 12 + 
                    self.end_date.month - self.start_date.month + 1
                )
            
            # Преобразуем в DataFrame
            df = pd.DataFrame(query)
            
            if df.empty:
                logger.warning("No sales data found for ABC analysis")
                return pd.DataFrame()
            
            # Добавляем расчетные поля
            total_revenue = df['total_revenue'].sum()
            df['revenue_share'] = df['total_revenue'] / total_revenue
            df['avg_monthly_revenue'] = df['total_revenue'] / months_count
            df['avg_monthly_quantity'] = df['total_quantity'] / months_count
            
            # Сортируем по убыванию выручки
            df = df.sort_values('revenue_share', ascending=False)
            
            # Рассчитываем кумулятивную долю
            df['cumulative_share'] = df['revenue_share'].cumsum()
            
            # Определяем категории
            df['category'] = 'C'
            df.loc[df['cumulative_share'] <= self.a_threshold, 'category'] = 'A'
            df.loc[(df['cumulative_share'] > self.a_threshold) & 
                  (df['cumulative_share'] <= self.b_threshold), 'category'] = 'B'
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting product sales data: {str(e)}")
            return pd.DataFrame()
    
    def get_detailed_analysis(self) -> Dict:
        """
        Получение подробного анализа продаж с дополнительными метриками
        """
        try:
            df = self.get_product_sales()
            if df.empty:
                return {'error': 'No data available for analysis'}
            
            # Расчет метрик по категориям
            category_metrics = {}
            for category in ['A', 'B', 'C']:
                cat_data = df[df['category'] == category]
                category_metrics[category] = {
                    'product_count': len(cat_data),
                    'revenue': safe_float(cat_data['total_revenue'].sum()),
                    'revenue_share': safe_float(cat_data['revenue_share'].sum()),
                    'quantity': safe_float(cat_data['total_quantity'].sum()),
                    'avg_monthly_revenue': safe_float(cat_data['avg_monthly_revenue'].mean()),
                    'avg_monthly_quantity': safe_float(cat_data['avg_monthly_quantity'].mean()),
                    'orders_count': int(cat_data['orders_count'].sum()) if len(cat_data) > 0 else 0,
                    'avg_price': safe_float(cat_data['avg_price'].mean()),
                    'products': []
                }
            
            # Добавляем детали по каждому продукту (используем to_dict для ~100x ускорения)
            for row in df.to_dict('records'):
                category = row['category']
                product_detail = {
                    'id': row['product__id'],
                    'name': row['product__name'],
                    'article': row['product__article'],
                    'group': row['product__group'],
                    'subgroup': row['product__subgroup'],
                    'revenue': safe_float(row['total_revenue']),
                    'revenue_share': safe_float(row['revenue_share']),
                    'cumulative_share': safe_float(row['cumulative_share']),
                    'quantity': safe_float(row['total_quantity']),
                    'avg_monthly_revenue': safe_float(row['avg_monthly_revenue']),
                    'avg_monthly_quantity': safe_float(row['avg_monthly_quantity']),
                    'orders_count': int(row['orders_count']) if row['orders_count'] else 0,
                    'avg_price': safe_float(row['avg_price'])
                }
                category_metrics[category]['products'].append(product_detail)
            
            # Общая статистика
            total_stats = {
                'total_revenue': float(df['total_revenue'].sum()),
                'total_quantity': float(df['total_quantity'].sum()),
                'total_products': len(df),
                'total_orders': int(df['orders_count'].sum())
            }
            
            return {
                'categories': category_metrics,
                'total_statistics': total_stats,
                'period': {
                    'start_date': self.start_date,
                    'end_date': self.end_date
                }
            }
            
        except Exception as e:
            logger.error(f"Error in detailed analysis: {str(e)}")
            return {'error': str(e)}