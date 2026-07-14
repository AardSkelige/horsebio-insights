# forecasting/services/prediction/group_predictor.py
from typing import Dict, List, Tuple
import pandas as pd
from forecasting.services.categorization.categorizer import CounterpartyCategorizator
from forecasting.services.prediction.prophet_predictor import ProphetPredictor
from django.db.models import Sum, F
from core.models import ShipmentItem
from django.db import models
from core.models import Counterparty

import logging

logger = logging.getLogger(__name__)

class GroupPredictor:
    def __init__(self, category: str = 'large'):
        self.category = category
        self.categorizer = CounterpartyCategorizator()
        
    def get_group_data(self) -> pd.DataFrame:
        """Получение агрегированных данных по группе"""
        try:
            # Получаем список контрагентов группы
            categories = self.categorizer.categorize()
            group_counterparties = categories.get(self.category, [])
            
            if not group_counterparties:
                logger.warning(f"Нет контрагентов в категории {self.category}")
                return pd.DataFrame()
            
            # Получаем все ID включая связанные
            counterparty_ids = []
            for c in group_counterparties:
                counterparty = Counterparty.objects.get(id=c['id'])
                counterparty_ids.extend(counterparty.all_related_ids)
            
            # Получаем агрегированные данные по месяцам
            shipments = ShipmentItem.objects.filter(
                shipment__counterparty_id__in=counterparty_ids
            ).values(
                'shipment__date'
            ).annotate(
                total_sum=Sum(F('price') * F('quantity'), output_field=models.DecimalField())
            ).order_by('shipment__date')
            
            # Преобразуем в DataFrame
            df = pd.DataFrame(shipments)
            if df.empty:
                return df
                
            df = df.rename(columns={'shipment__date': 'date', 'total_sum': 'total_sum'})
            df['total_sum'] = df['total_sum'].astype(float)
            df.set_index('date', inplace=True)
            
            # Ресемплируем по месяцам
            df_monthly = df.resample('M').sum()
            
            return df_monthly
            
        except Exception as e:
            logger.error(f"Ошибка получения данных группы: {str(e)}")
            return pd.DataFrame()
    
    def predict(self, periods: int = 3) -> Dict:
        """Прогноз для группы"""
        try:
            df = self.get_group_data()
            if df.empty:
                return {'error': 'Нет данных для прогноза'}
            
            predictor = ProphetPredictor(df)
            result = predictor.train_and_predict(periods)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования для группы: {str(e)}")
            return {'error': str(e)}