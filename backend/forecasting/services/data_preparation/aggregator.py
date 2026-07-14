# forecasting/services/data_preparation/aggregator.py
from typing import Dict, Tuple
import pandas as pd
import numpy as np
from django.db.models import Sum, F
from django.utils import timezone
from dateutil.relativedelta import relativedelta
import logging

from core.models import ShipmentItem, Counterparty

logger = logging.getLogger(__name__)

class DataAggregator:
    @staticmethod
    def _handle_outliers(df: pd.DataFrame) -> pd.DataFrame:
        """Обработка выбросов методом IQR с более мягким коэффициентом"""
        Q1 = df['total_sum'].quantile(0.25)
        Q3 = df['total_sum'].quantile(0.75)
        IQR = Q3 - Q1
        
        # Увеличиваем коэффициент с 1.5 до 2.5
        lower_bound = Q1 - 2.5 * IQR
        upper_bound = Q3 + 2.5 * IQR
        
        # Заменяем только очень сильные выбросы
        df.loc[df['total_sum'] > upper_bound, 'total_sum'] = upper_bound
        df.loc[df['total_sum'] < lower_bound, 'total_sum'] = lower_bound
        
        return df

    @staticmethod
    def _handle_zeros(df: pd.DataFrame) -> pd.DataFrame:
        """Замена нулевых значений на медиану"""
        median_value = df[df['total_sum'] > 0]['total_sum'].median()
        df.loc[df['total_sum'] == 0, 'total_sum'] = median_value
        return df

    @staticmethod
    def get_counterparty_data(counterparty_id: int) -> Tuple[pd.DataFrame, Dict]:
        """Получение и очистка данных по контрагенту"""
        try:
            counterparty = Counterparty.objects.get(id=counterparty_id)
            related_ids = counterparty.all_related_ids
            
            end_date = timezone.now()
            start_date = end_date - relativedelta(months=24)
            
            logger.info(f"Анализ контрагента {counterparty.name} (ID: {counterparty.id})")
            
            # Получаем данные
            shipments = ShipmentItem.objects.filter(
                shipment__counterparty_id__in=related_ids,
                shipment__date__gte=start_date,
                shipment__date__lte=end_date
            ).values(
                'shipment__date',
                'shipment__counterparty_id'
            ).annotate(
                total_sum=Sum(F('price') * F('quantity'))
            ).order_by('shipment__date')

            if not shipments:
                return pd.DataFrame(), {'error': 'Нет данных'}

            # Создаем DataFrame
            df = pd.DataFrame(shipments)
            df['total_sum'] = df['total_sum'].astype(float)
            df = df.rename(columns={'shipment__date': 'date'})

            # Группируем по дате
            df = df.groupby('date')['total_sum'].sum().reset_index()
            
            # Сохраняем оригинальные данные для сравнения
            original_sum = df['total_sum'].sum()
            
            # Очистка данных
            df = DataAggregator._handle_outliers(df)
            df = DataAggregator._handle_zeros(df)
            
            cleaned_sum = df['total_sum'].sum()
            
            # Устанавливаем индекс и ресемплируем
            df.set_index('date', inplace=True)
            df_resampled = df.resample('M').sum()
            
            # Статистика и метаданные
            metadata = {
                'start_date': df_resampled.index.min(),
                'end_date': df_resampled.index.max(),
                'data_points': len(df_resampled),
                'total_sum': float(df_resampled['total_sum'].sum()),
                'mean': float(df_resampled['total_sum'].mean()),
                'original_sum': float(original_sum),
                'cleaning_diff_pct': ((cleaned_sum - original_sum) / original_sum) * 100
            }
            
            logger.info(f"Обработано {metadata['data_points']} месяцев")
            logger.info(f"Изменение после очистки: {metadata['cleaning_diff_pct']:.2f}%")
            
            return df_resampled, metadata
            
        except Exception as e:
            logger.error(f"Ошибка получения данных: {str(e)}")
            return pd.DataFrame(), {'error': str(e)}