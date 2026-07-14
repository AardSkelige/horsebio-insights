# forecasting/services/prediction/small_group_predictor.py
from typing import Dict
import pandas as pd
from forecasting.services.categorization.categorizer import CounterpartyCategorizator
from forecasting.services.prediction.prophet_predictor import ProphetPredictor
from django.db.models import Sum, F
from django.db import models
from core.models import ShipmentItem, Counterparty
import logging

logger = logging.getLogger(__name__)

class SmallGroupPredictor:
    def __init__(self):
        self.categorizer = CounterpartyCategorizator()
        
    def get_group_data(self) -> pd.DataFrame:
        """Получение агрегированных данных по мелкой группе"""
        try:
            # Получаем список мелких контрагентов
            categories = self.categorizer.categorize()
            small_counterparties = categories.get('small', [])
            
            if not small_counterparties:
                logger.warning("Нет контрагентов в мелкой категории")
                return pd.DataFrame()
            
            # Получаем все ID включая связанные
            counterparty_ids = []
            for c in small_counterparties:
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
            
            # Заполняем пропуски нулями, так как у мелких клиентов много пропущенных месяцев
            df_monthly = df_monthly.fillna(0)
            
            return df_monthly
            
        except Exception as e:
            logger.error(f"Ошибка получения данных мелкой группы: {str(e)}")
            return pd.DataFrame()
    
    def predict(self, periods: int = 2) -> Dict:  # Уменьшаем горизонт прогноза для мелких
        """Прогноз для мелкой группы"""
        try:
            df = self.get_group_data()
            if df.empty:
                return {'error': 'Нет данных для прогноза'}
            
            predictor = ProphetPredictor(df)
            result = predictor.train_and_predict(periods)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования для мелкой группы: {str(e)}")
            return {'error': str(e)}