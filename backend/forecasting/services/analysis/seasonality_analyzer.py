# forecasting/services/analysis/seasonality_analyzer.py

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from django.db.models import Sum, F, Count
from django.db import models
from datetime import datetime
import logging
from statsmodels.tsa.seasonal import seasonal_decompose
from core.models import ShipmentItem, Product

logger = logging.getLogger(__name__)

class SeasonalityAnalyzer:
    """
    Анализатор сезонности продаж продуктов
    """
    
    SEASONALITY_TYPES = {
        'STABLE': 'Стабильные продажи',
        'SUMMER': 'Летний сезон',
        'WINTER': 'Зимний сезон',
        'MULTI_PEAK': 'Несколько пиков',
        'UNCERTAIN': 'Неопределенная сезонность'
    }

    def __init__(self, min_months: int = 12):
        self.min_months = min_months
        
    def get_product_monthly_sales(self, product_id: int) -> pd.DataFrame:
        """
        Получение помесячных продаж для продукта
        """
        try:
            # Сначала проверим есть ли вообще продажи
            sales_exist = ShipmentItem.objects.filter(
                product_id=product_id,
                shipment__date__isnull=False
            ).exists()
            
            if not sales_exist:
                logger.warning(f"No sales found for product {product_id}")
                return pd.DataFrame()

            # Получаем все продажи с детальной информацией
            sales_data = list(ShipmentItem.objects.filter(
                product_id=product_id,
                shipment__date__isnull=False
            ).values(
                'shipment__date',
                'quantity',
                'price'
            ).order_by('shipment__date'))
            
            if not sales_data:
                return pd.DataFrame()
                
            # Преобразуем данные в DataFrame
            df = pd.DataFrame(sales_data)
            df['date'] = pd.to_datetime(df['shipment__date'])
            df['revenue'] = df['price'].astype(float) * df['quantity'].astype(float)
            
            # Группируем по месяцам
            monthly_data = df.groupby(pd.Grouper(key='date', freq='M')).agg({
                'quantity': 'sum',
                'revenue': 'sum'
            })
            
            # Проверяем результат
            logger.info(f"Product {product_id} monthly data:")
            logger.info(f"Total months: {len(monthly_data)}")
            logger.info(f"Total quantity: {monthly_data['quantity'].sum()}")
            logger.info(f"Total revenue: {monthly_data['revenue'].sum()}")
            
            return monthly_data

        except Exception as e:
            logger.error(f"Error getting monthly sales for product {product_id}: {str(e)}")
            logger.exception("Detailed error:")  # Это выведет полный стек ошибки
            return pd.DataFrame()

    def analyze_seasonality(self, df: pd.DataFrame) -> Dict:
        """
        Анализ сезонности на основе данных продаж
        """
        try:
            if df.empty or len(df) < self.min_months:
                return {
                    'seasonality_type': 'UNCERTAIN',
                    'reason': 'Недостаточно данных для анализа',
                    'confidence': 0
                }

            # Используем количество для анализа сезонности
            quantity_series = df['quantity'].astype(float)
            
            # Проверяем, есть ли ненулевые значения
            if quantity_series.sum() == 0:
                return {
                    'seasonality_type': 'UNCERTAIN',
                    'reason': 'Нет данных о продажах',
                    'confidence': 0
                }

            # Выполняем декомпозицию временного ряда
            period = min(12, len(df) // 2)  # Корректируем период если данных мало
            decomposition = seasonal_decompose(
                quantity_series,
                period=period,
                extrapolate_trend='freq'
            )
            
            # Получаем сезонную компоненту
            seasonal = decomposition.seasonal
            
            # Рассчитываем среднее для каждого месяца
            monthly_averages = []
            for month in range(1, 13):
                month_data = seasonal[seasonal.index.month == month]
                if not month_data.empty:
                    monthly_averages.append(float(month_data.mean()))
                else:
                    monthly_averages.append(0)
            
            # Нормализуем средние значения
            if monthly_averages:
                mean_value = np.mean(monthly_averages)
                normalized_averages = [x - mean_value for x in monthly_averages]
                
                # Определяем тип сезонности
                summer_months = normalized_averages[5:8]  # Июнь-Август
                winter_months = normalized_averages[11:] + normalized_averages[:2]  # Декабрь-Февраль
                
                seasonality_strength = np.std(normalized_averages)
                summer_strength = np.mean(summer_months)
                winter_strength = np.mean(winter_months)
                
                peaks = len([i for i in range(1, len(normalized_averages)-1)
                            if normalized_averages[i-1] < normalized_averages[i] > normalized_averages[i+1]])
                
                if seasonality_strength < 0.1:
                    seasonality_type = 'STABLE'
                    confidence = 0.8
                elif peaks >= 2:
                    seasonality_type = 'MULTI_PEAK'
                    confidence = 0.7
                elif summer_strength > winter_strength and summer_strength > 0.15:
                    seasonality_type = 'SUMMER'
                    confidence = 0.75
                elif winter_strength > summer_strength and winter_strength > 0.15:
                    seasonality_type = 'WINTER'
                    confidence = 0.75
                else:
                    seasonality_type = 'UNCERTAIN'
                    confidence = 0.5

                return {
                    'seasonality_type': seasonality_type,
                    'confidence': confidence,
                    'metrics': {
                        'seasonality_strength': float(seasonality_strength),
                        'summer_strength': float(summer_strength),
                        'winter_strength': float(winter_strength),
                        'peaks': peaks
                    },
                    'monthly_averages': monthly_averages,
                    'normalized_averages': normalized_averages
                }
            else:
                return {
                    'seasonality_type': 'UNCERTAIN',
                    'reason': 'Не удалось рассчитать средние значения',
                    'confidence': 0
                }

        except Exception as e:
            logger.error(f"Error in seasonality analysis: {str(e)}")
            return {
                'seasonality_type': 'UNCERTAIN',
                'reason': str(e),
                'confidence': 0
            }

    def analyze_product(self, product_id: int) -> Dict:
        """
        Полный анализ сезонности для продукта
        """
        try:
            # Получаем данные о продукте
            product = Product.objects.get(id=product_id)
            
            # Получаем данные о продажах
            sales_df = self.get_product_monthly_sales(product_id)
            
            if sales_df.empty:
                return {
                    'error': 'Нет данных о продажах',
                    'product_id': product_id
                }
            
            # Анализируем сезонность
            seasonality = self.analyze_seasonality(sales_df)
            
            # Рассчитываем базовую статистику
            if 'quantity' in sales_df.columns:
                total_quantity = float(sales_df['quantity'].sum())
                avg_monthly_quantity = float(sales_df['quantity'].mean())
            else:
                total_quantity = 0
                avg_monthly_quantity = 0
                
            if 'revenue' in sales_df.columns:
                total_revenue = float(sales_df['revenue'].sum())
                avg_monthly_revenue = float(sales_df['revenue'].mean())
            else:
                total_revenue = 0
                avg_monthly_revenue = 0

            return {
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'article': product.article,
                    'group': product.group
                },
                'sales_data': {
                    'total_quantity': total_quantity,
                    'total_revenue': total_revenue,
                    'months_count': len(sales_df),
                    'avg_monthly_quantity': avg_monthly_quantity,
                    'avg_monthly_revenue': avg_monthly_revenue
                },
                'seasonality': seasonality
            }

        except Product.DoesNotExist:
            logger.error(f"Product {product_id} not found")
            return {'error': 'Продукт не найден'}
        except Exception as e:
            logger.error(f"Error analyzing product {product_id}: {str(e)}")
            return {'error': str(e)}