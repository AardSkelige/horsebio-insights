# forecasting/services/prediction/prophet_predictor.py
from prophet import Prophet
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class ProphetPredictor:
    def __init__(self, df: pd.DataFrame):
        """
        df: DataFrame с колонкой 'total_sum' и датами в индексе
        """
        self.df = df
        self.model = None
        
    def prepare_data(self) -> pd.DataFrame:
        """Подготовка данных для Prophet"""
        prophet_df = pd.DataFrame({
            'ds': self.df.index.tz_localize(None),
            'y': self.df['total_sum']
        })
        return prophet_df
        
    # forecasting/services/prediction/prophet_predictor.py
    def train_and_predict(self, periods: int = None) -> dict:
        try:
            prophet_df = self.prepare_data()
            
            # Определяем период прогноза на основе длины данных
            data_months = len(self.df)
            # Если данных меньше года, прогнозируем только на 1 месяц
            forecast_periods = 1 if data_months < 12 else 3
            if periods is not None:
                forecast_periods = periods
                
            # Настраиваем модель
            self.model = Prophet(
                yearly_seasonality=True if data_months >= 12 else False,  # сезонность только если есть год данных
                weekly_seasonality=False,
                daily_seasonality=False,
                growth='linear'  # используем линейный рост
            )
            
            self.model.fit(prophet_df)
            
            # Создание фрейма для прогноза
            future_dates = self.model.make_future_dataframe(
                periods=forecast_periods, 
                freq='M'
            )
            
            forecast = self.model.predict(future_dates)
            
            # Обрезаем отрицательные значения
            forecast['yhat'] = forecast['yhat'].clip(lower=0)
            forecast['yhat_lower'] = forecast['yhat_lower'].clip(lower=0)
            forecast['yhat_upper'] = forecast['yhat_upper'].clip(lower=0)
            
            return {
                'forecast': forecast,
                'history': prophet_df,
                'model': self.model,
                'periods': forecast_periods
            }
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования: {str(e)}")
            return {'error': str(e)}