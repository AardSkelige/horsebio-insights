# forecasting/services/categorization/categorizer.py
from collections import defaultdict
from decimal import Decimal
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
        """Помесячная статистика по каждому контрагенту.

        Ошибки наружу не глушим. Пустой DataFrame — законный ответ (никто
        ничего не отгружал), и подменять им поломку значит показывать
        пустой отчёт вместо сообщения о сбое: страница выглядит рабочей,
        а расчёта нет. Вызывающий и так заворачивает исключение в ошибку
        раздела и пишет трассировку в лог.
        """
        # Раньше здесь шёл обход контрагентов, и на каждого приходилось три
        # запроса: список его старых карточек, общая сумма и помесячная
        # разбивка. На проде это больше двух тысяч контрагентов, то есть
        # свыше шести тысяч запросов на один расчёт.
        #
        # Теперь всё то же считается одной группировкой по контрагенту и
        # месяцу, а склейка старых карточек с основными делается по карте,
        # вычитанной одним запросом.
        names = dict(
            Counterparty.objects.filter(is_legacy=False).values_list('id', 'name')
        )

        # Старая карточка отдаёт свои отгрузки основной — так же, как это
        # делал `all_related_ids`.
        owner = {counterparty_id: counterparty_id for counterparty_id in names}
        legacy_pairs = Counterparty.objects.filter(
            is_legacy=True, main_counterparty_id__isnull=False
        ).values_list('id', 'main_counterparty_id')
        for legacy_id, main_id in legacy_pairs:
            if main_id in names:
                owner[legacy_id] = main_id

        shipments_query = ShipmentItem.objects.filter(
            shipment__counterparty_id__in=owner.keys()
        )
        if self.start_date:
            shipments_query = shipments_query.filter(
                shipment__date__gte=self.start_date
            )
        if self.end_date:
            shipments_query = shipments_query.filter(
                shipment__date__lte=self.end_date
            )

        monthly_rows = shipments_query.annotate(
            year=ExtractYear('shipment__date'),
            month=ExtractMonth('shipment__date')
        ).values(
            'shipment__counterparty_id', 'year', 'month'
        ).annotate(
            monthly_sum=Sum(F('price') * F('quantity'),
                            output_field=models.DecimalField())
        ).order_by()

        # Контрагент → {(год, месяц): сумма}. Месяц, в котором отгружались
        # и основная карточка, и старая, остаётся одним месяцем — как и
        # при прежней группировке по объединённому списку идентификаторов.
        by_counterparty = defaultdict(dict)
        for row in monthly_rows:
            main_id = owner[row['shipment__counterparty_id']]
            month_key = (row['year'], row['month'])
            months = by_counterparty[main_id]
            months[month_key] = months.get(month_key, Decimal('0')) + (
                row['monthly_sum'] or Decimal('0')
            )

        all_stats = []
        for counterparty_id, months in by_counterparty.items():
            monthly_values = [float(value) for value in months.values()]
            total_months = len(monthly_values)
            active_months = len([value for value in monthly_values if value > 0])
            total_sum = float(sum(months.values()))

            all_stats.append({
                'counterparty_id': counterparty_id,
                'name': names[counterparty_id],
                'total_months': total_months,
                'active_months': active_months,
                'total_sum': total_sum,
                'frequency': active_months / total_months if total_months > 0 else 0,
                'avg_monthly': total_sum / active_months if active_months > 0 else 0
            })

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