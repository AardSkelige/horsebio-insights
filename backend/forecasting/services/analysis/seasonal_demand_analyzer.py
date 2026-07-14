# forecasting/services/analysis/seasonal_demand_analyzer.py

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from django.db.models import Sum, F, Avg, Min, Max
from decimal import Decimal
from django.db import models
import logging
from datetime import datetime, timedelta
from django.utils import timezone
import matplotlib.pyplot as plt

from core.models import (
    Product, 
    ShipmentItem
)

logger = logging.getLogger(__name__)

class SeasonalDemandAnalyzer:
    """
    Анализатор сезонной потребности в продуктах.
    Создает прогноз с учетом сезонности для последующего анализа потребности в компонентах.
    """
    
    SEASON_TYPES = {
        'STABLE': 'Стабильные продажи',
        'SUMMER': 'Летний сезон',
        'WINTER': 'Зимний сезон',
        'MULTI_PEAK': 'Несколько пиков',
        'UNCERTAIN': 'Неопределенная сезонность'
    }
    
    def __init__(self, start_date=None, end_date=None, forecast_months: int = 12):
        self.start_date = start_date
        self.end_date = end_date
        self.forecast_months = forecast_months
        
    def get_sales_history(self, product_id: int) -> pd.DataFrame:
        """
        Получение истории продаж по месяцам
        """
        try:
            sales = ShipmentItem.objects.filter(
                product_id=product_id,
                shipment__date__range=(self.start_date, self.end_date)
            ).values(
                'shipment__date__year',
                'shipment__date__month'
            ).annotate(
                monthly_qty=Sum('quantity')
            ).order_by('shipment__date__year', 'shipment__date__month')
            
            if not sales:
                return pd.DataFrame()
                
            # Преобразуем в DataFrame
            df = pd.DataFrame(sales)
            
            # Преобразуем Decimal в float
            df['monthly_qty'] = df['monthly_qty'].astype(float)
            
            # Формируем дату в правильном формате
            df['date'] = pd.to_datetime(
                df.apply(
                    lambda x: f"{int(x['shipment__date__year'])}-{int(x['shipment__date__month'])}-01",
                    axis=1
                )
            )
            
            # Устанавливаем дату как индекс
            df = df.set_index('date')
            df = df['monthly_qty'].resample('ME').sum().fillna(0)
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting sales history for product {product_id}: {str(e)}")
            logger.exception("Full traceback:")
            return pd.DataFrame()
    def visualize_sales(self, sales_history: pd.Series, title: str = '') -> plt.Figure:
        """
        Создает визуализацию продаж с трендом и сезонностью
        """
        try:
            # Создаем фигуру большего размера для лучшей читаемости
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
            
            # График продаж
            ax1.plot(sales_history.index, sales_history.values, 
                    marker='o', linestyle='-', linewidth=2, markersize=6)
            ax1.set_title(f'Динамика продаж: {title}')
            ax1.set_xlabel('Период')
            ax1.set_ylabel('Количество')
            ax1.grid(True)
            
            # Поворачиваем метки дат для лучшей читаемости
            ax1.tick_params(axis='x', rotation=45)
            
            # График сезонности (относительно среднего)
            monthly_avg = sales_history.groupby(sales_history.index.month).mean()
            overall_avg = sales_history.mean()
            seasonal_factors = monthly_avg / overall_avg
            
            ax2.bar(range(1, 13), [seasonal_factors.get(m, 0) for m in range(1, 13)])
            ax2.axhline(y=1, color='r', linestyle='--', alpha=0.5)
            ax2.set_title('Сезонные коэффициенты по месяцам')
            ax2.set_xlabel('Месяц')
            ax2.set_ylabel('Отношение к среднему')
            ax2.grid(True, axis='y')
            
            # Добавляем метки месяцев
            month_labels = ['Янв', 'Фев', 'Март', 'Апр', 'Май', 'Июнь', 
                        'Июль', 'Авг', 'Сент', 'Окт', 'Ноя', 'Дек']
            ax2.set_xticks(range(1, 13))
            ax2.set_xticklabels(month_labels, rotation=45)
            
            plt.tight_layout()
            return fig
            
        except Exception as e:
            logger.error(f"Error creating visualization: {str(e)}")
            logger.exception("Full traceback:")
            return None
        
    def analyze_seasonality_pattern(self, sales_history: pd.Series) -> Dict:
        """
        Анализирует паттерн сезонности на основе исторических данных
        """
        try:
            if sales_history.empty:
                return {
                    'error': 'Нет данных для анализа'
                }

            # Расчет сезонных коэффициентов
            monthly_avg = sales_history.groupby(sales_history.index.month).mean()
            overall_avg = sales_history.mean()

            # Защита от деления на ноль и обработка особых случаев
            if overall_avg == 0 or np.isnan(overall_avg):
                return {
                    'seasonality_type': 'UNCERTAIN',
                    'seasonal_factors': {month: 1.0 for month in range(1, 13)},
                    'peaks': [],
                    'troughs': [],
                    'stability_metrics': {
                        'coefficient_std': 0,
                        'max_deviation': 0,
                        'peaks_count': 0,
                        'troughs_count': 0
                    }
                }

            # Расчет и очистка сезонных коэффициентов
            seasonal_factors = (monthly_avg / overall_avg).round(2)
            seasonal_factors = seasonal_factors.replace([np.inf, -np.inf], 1.0)
            seasonal_factors = seasonal_factors.fillna(1.0)

            # Определение значимых отклонений (>20% от среднего)
            significant_peaks = seasonal_factors[seasonal_factors > 1.2]
            significant_troughs = seasonal_factors[seasonal_factors < 0.8]

            # Определение типа сезонности
            if len(significant_peaks) >= 2:
                seasonality_type = 'MULTI_PEAK'
            elif len(significant_peaks) == 1:
                peak_month = significant_peaks.index[0]
                if 5 <= peak_month <= 8:  # Май-Август
                    seasonality_type = 'SUMMER'
                elif peak_month in [12, 1, 2]:  # Декабрь-Февраль
                    seasonality_type = 'WINTER'
                else:
                    seasonality_type = 'SINGLE_PEAK'
            elif seasonal_factors.std() < 0.2:  # Небольшие колебания
                seasonality_type = 'STABLE'
            else:
                seasonality_type = 'UNCERTAIN'

            # Анализ пиков с проверкой значений
            peaks_analysis = []
            for month, factor in significant_peaks.items():
                if not np.isnan(factor) and not np.isinf(factor):
                    peaks_analysis.append({
                        'month': month,
                        'coefficient': float(factor),
                        'deviation_percent': float((factor - 1) * 100)
                    })

            # Анализ спадов с проверкой значений
            troughs_analysis = []
            for month, factor in significant_troughs.items():
                if not np.isnan(factor) and not np.isinf(factor):
                    troughs_analysis.append({
                        'month': month,
                        'coefficient': float(factor),
                        'deviation_percent': float((factor - 1) * 100)
                    })

            # Расчет метрик с защитой от особых значений
            std_value = seasonal_factors.std()
            max_dev = abs(seasonal_factors - 1).max()

            return {
                'seasonality_type': seasonality_type,
                'seasonal_factors': {
                    month: float(factor) if not np.isnan(factor) and not np.isinf(factor) else 1.0
                    for month, factor in seasonal_factors.items()
                },
                'peaks': peaks_analysis,
                'troughs': troughs_analysis,
                'stability_metrics': {
                    'coefficient_std': float(std_value) if not np.isnan(std_value) else 0,
                    'max_deviation': float(max_dev) if not np.isnan(max_dev) else 0,
                    'peaks_count': len(peaks_analysis),
                    'troughs_count': len(troughs_analysis)
                }
            }

        except Exception as e:
            logger.error(f"Error analyzing seasonality pattern: {str(e)}")
            logger.exception("Full traceback:")
            return {'error': str(e)}