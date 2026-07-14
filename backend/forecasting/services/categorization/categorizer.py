# forecasting/services/categorization/categorizer.py
from typing import Dict, List
import pandas as pd
import numpy as np
from django.db.models import Avg, Count, Sum, F
from django.db.models.functions import ExtractYear, ExtractMonth
from core.models import Counterparty, ShipmentItem
from django.db import models
import logging

logger = logging.getLogger(__name__)

class CounterpartyCategorizator:
    CATEGORIES = {
        'large': 'Крупный (регулярные закупки)',
        'medium': 'Средний (регулярные закупки)',
        'small': 'Мелкий (нерегулярные закупки)',
        'rare_large': 'Крупный (редкие закупки)'
    }
    
    def __init__(self, start_date=None, end_date=None):
        self.stats = {}
        self.start_date = start_date
        self.end_date = end_date
    
    def calculate_statistics(self) -> pd.DataFrame:
        try:
            all_stats = []
            counterparties = Counterparty.objects.filter(is_legacy=False)
            
            for counterparty in counterparties:
                related_ids = counterparty.all_related_ids
                
                # Базовый запрос с учетом периода
                shipments_query = ShipmentItem.objects.filter(
                    shipment__counterparty_id__in=related_ids
                )
                
                # Добавляем фильтры по датам
                if self.start_date:
                    shipments_query = shipments_query.filter(
                        shipment__date__gte=self.start_date
                    )
                if self.end_date:
                    shipments_query = shipments_query.filter(
                        shipment__date__lte=self.end_date
                    )

                # Получаем суммарные значения за период
                total_data = shipments_query.aggregate(
                    total_sum=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
                )
                
                # Получаем помесячную статистику с учетом периода
                monthly_stats = shipments_query.annotate(
                    year=ExtractYear('shipment__date'),
                    month=ExtractMonth('shipment__date')
                ).values(
                    'year', 
                    'month'
                ).annotate(
                    monthly_sum=Sum(F('price') * F('quantity'))
                ).order_by('year', 'month')
                
                if monthly_stats:
                    monthly_values = [float(s['monthly_sum'] or 0) for s in monthly_stats]
                    total_months = len(monthly_stats)
                    active_months = len([v for v in monthly_values if v > 0])
                    total_sum = float(total_data['total_sum'] or 0)
                    
                    stats = {
                        'counterparty_id': counterparty.id,
                        'name': counterparty.name,
                        'total_months': total_months,
                        'active_months': active_months,
                        'total_sum': total_sum,
                        'frequency': active_months / total_months if total_months > 0 else 0,
                        'avg_monthly': total_sum / active_months if active_months > 0 else 0
                    }
                    all_stats.append(stats)
            
            # Создаем DataFrame со всеми нужными колонками
            columns = ['counterparty_id', 'name', 'total_months', 'active_months', 
                      'total_sum', 'frequency', 'avg_monthly']
            self.stats_df = pd.DataFrame(all_stats, columns=columns)
            
            # Рассчитываем границы для категорий
            if not self.stats_df.empty:
                monthly_values = self.stats_df['avg_monthly']
                self.thresholds = {
                    'monthly_volume': {
                        'small': monthly_values.quantile(0.25),
                        'medium': monthly_values.quantile(0.75),
                        'large': monthly_values.quantile(0.95)
                    },
                    'frequency': {
                        'rare': 0.25,
                        'regular': 0.75
                    }
                }
                
            return self.stats_df
            
        except Exception as e:
            return pd.DataFrame()

    def categorize(self) -> Dict[str, List]:
        if not hasattr(self, 'stats_df') or self.stats_df.empty:
            self.calculate_statistics()
        
        if not hasattr(self, 'thresholds'):
            return {}
            
        categories = {cat: [] for cat in self.CATEGORIES.keys()}
        
        for _, row in self.stats_df.iterrows():
            # Определяем категорию
            if row['avg_monthly'] >= self.thresholds['monthly_volume']['large']:
                if row['frequency'] >= self.thresholds['frequency']['regular']:
                    category = 'large'
                else:
                    category = 'rare_large'
            elif row['avg_monthly'] >= self.thresholds['monthly_volume']['medium']:
                if row['frequency'] >= self.thresholds['frequency']['regular']:
                    category = 'medium'
                else:
                    category = 'small'
            else:
                category = 'small'
            

            categories[category].append({
                'id': row['counterparty_id'],
                'name': row['name'],
                'avg_monthly': row['avg_monthly'],
                'frequency': row['frequency'],
                'total_months': row['total_months'],
                'total_sum': row['total_sum']
            })
        
        # Сортируем каждую категорию по среднемесячному объему
        for category in categories:
            categories[category] = sorted(
                categories[category],
                key=lambda x: x['avg_monthly'],
                reverse=True
            )
        return categories