# forecasting/services/prediction/medium_group_predictor.py
from typing import Dict
import pandas as pd
from forecasting.services.categorization.categorizer import CounterpartyCategorizator
from forecasting.services.prediction.prophet_predictor import ProphetPredictor
from django.db.models import Sum, F
from django.db import models
from core.models import ShipmentItem, Counterparty
import logging

logger = logging.getLogger(__name__)

class MediumGroupPredictor:
    def __init__(self):
        self.categorizer = CounterpartyCategorizator()
        
    def get_group_data(self) -> pd.DataFrame:
        """Получение агрегированных данных по средней группе"""
        try:
            # Получаем список средних контрагентов
            categories = self.categorizer.categorize()
            medium_counterparties = categories.get('medium', [])
            
            if not medium_counterparties:
                logger.warning("Нет контрагентов в средней категории")
                return pd.DataFrame()
            
            # Получаем все ID включая связанные
            counterparty_ids = []
            for c in medium_counterparties:
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
            logger.error(f"Ошибка получения данных средней группы: {str(e)}")
            return pd.DataFrame()
    
    def predict(self, periods: int = 3) -> Dict:
        """Прогноз для средней группы"""
        try:
            df = self.get_group_data()
            if df.empty:
                return {'error': 'Нет данных для прогноза'}
            
            predictor = ProphetPredictor(df)
            result = predictor.train_and_predict(periods)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования для средней группы: {str(e)}")
            return {'error': str(e)}