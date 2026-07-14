# forecasting/services/analysis/time_series.py
import pandas as pd
import numpy as np
from statsmodels.tsa.seasonal import seasonal_decompose
import matplotlib.pyplot as plt
import seaborn as sns
import logging

logger = logging.getLogger(__name__)

class TimeSeriesAnalyzer:
    def __init__(self, df: pd.DataFrame):
        self.df = df
    
    def plot_time_series(self):
        """Построение базового графика временного ряда"""
        plt.figure(figsize=(15, 7))
        plt.plot(self.df.index, self.df['total_sum'])
        plt.title('Динамика продаж')
        plt.xlabel('Дата')
        plt.ylabel('Объем продаж')
        plt.grid(True)
        return plt
        
    def decompose_series(self):
        try:
            ts = self.df['total_sum'].fillna(method='ffill')
            
            # Определяем период на основе длины данных
            period = min(12, len(ts) // 2)  # период не больше 12 и не больше половины длины ряда
            
            decomposition = seasonal_decompose(
                ts, 
                period=period,
                extrapolate_trend='freq'
            )
            
            fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(15, 12))
            
            decomposition.observed.plot(ax=ax1)
            ax1.set_title('Исходный ряд')
            ax1.grid(True)
            
            decomposition.trend.plot(ax=ax2)
            ax2.set_title('Тренд')
            ax2.grid(True)
            
            decomposition.seasonal.plot(ax=ax3)
            ax3.set_title('Сезонность')
            ax3.grid(True)
            
            decomposition.resid.plot(ax=ax4)
            ax4.set_title('Остатки')
            ax4.grid(True)
            
            plt.tight_layout()
            return plt, decomposition
            
        except Exception as e:
            logger.error(f"Ошибка при декомпозиции: {str(e)}")
            return None, None