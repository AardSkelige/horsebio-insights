# forecasting/services/prediction/predictor.py
from typing import Dict, Tuple
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
import logging

logger = logging.getLogger(__name__)

class BasePredictor:
    def __init__(self, df: pd.DataFrame):
        """
        df: DataFrame с колонкой 'total_sum' и датами в индексе
        """
        self.df = df
        self.model = LinearRegression()
        
    def prepare_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Подготовка данных для прогноза"""
        # Создаем числовые признаки из дат (месяцы с начала периода)
        self.df['months'] = range(len(self.df))
        
        X = self.df['months'].values.reshape(-1, 1)
        y = self.df['total_sum'].values
        
        # Определяем точку разделения (80%)
        split_point = int(len(self.df) * 0.8)
        
        return X[:split_point], y[:split_point]
    
    def train_and_predict(self) -> Dict:
        """Обучение модели и прогноз"""
        try:
            # Подготовка данных
            X_train, y_train = self.prepare_data()
            
            # Обучение модели
            self.model.fit(X_train, y_train)
            
            # Прогноз на все точки для сравнения
            X_all = self.df['months'].values.reshape(-1, 1)
            predictions = self.model.predict(X_all)
            
            # Прогноз на следующие 3 месяца
            future_months = np.array(range(len(self.df), len(self.df) + 3))
            future_predictions = self.model.predict(future_months.reshape(-1, 1))
            
            # Расчет метрик
            train_predictions = predictions[:len(X_train)]
            mae = mean_absolute_error(y_train, train_predictions)
            mse = mean_squared_error(y_train, train_predictions)
            rmse = np.sqrt(mse)
            
            # Коэффициент детерминации
            r2 = self.model.score(X_train, y_train)
            
            return {
                'predictions': predictions,
                'future_predictions': future_predictions,
                'metrics': {
                    'mae': mae,
                    'rmse': rmse,
                    'r2': r2,
                    'slope': self.model.coef_[0],
                    'intercept': self.model.intercept_
                }
            }
            
        except Exception as e:
            logger.error(f"Ошибка прогнозирования: {str(e)}")
            return {'error': str(e)}
        
# forecasting/services/prediction/predictor.py
from typing import Dict, Tuple, List
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
class AdvancedPredictor:
    def __init__(self, df: pd.DataFrame, max_degree: int = 3):
        """
        df: DataFrame с колонкой 'total_sum' и датами в индексе
        max_degree: максимальная степень полинома (ограничена до 3)
        """
        self.df = df
        self.max_degree = min(max_degree, 3)  # Ограничиваем степень
        self.best_model = None
        self.best_degree = None
        self.best_poly_features = None
        
        # Вычисляем бизнес-ограничения
        self.min_value = df['total_sum'].min()
        self.max_value = df['total_sum'].max()
        self.mean_value = df['total_sum'].mean()
        self.max_monthly_change = self.mean_value * 0.5  # Максимальное изменение 50% от среднего
        
    def _validate_prediction(self, predictions: np.ndarray, last_actual: float) -> np.ndarray:
        """Проверка и корректировка прогноза"""
        validated = []
        current = last_actual
        
        for pred in predictions:
            # Ограничение по минимальному значению
            pred = max(pred, self.min_value)
            
            # Ограничение по максимальному изменению
            max_up = current + self.max_monthly_change
            max_down = max(current - self.max_monthly_change, self.min_value)
            pred = min(max(pred, max_down), max_up)
            
            validated.append(pred)
            current = pred
            
        return np.array(validated)
    
    def prepare_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """Подготовка данных для прогноза"""
        self.df['months'] = range(len(self.df))
        X = self.df['months'].values.reshape(-1, 1)
        y = self.df['total_sum'].values
        
        split_point = int(len(self.df) * 0.8)
        return X[:split_point], y[:split_point]
    
    def find_best_model(self) -> Dict:
        """Подбор лучшей модели среди полиномов разных степеней"""
        X_train, y_train = self.prepare_data()
        best_score = -np.inf
        results = []
        
        for degree in range(1, self.max_degree + 1):
            poly_features = PolynomialFeatures(degree=degree)
            X_poly = poly_features.fit_transform(X_train)
            
            model = LinearRegression()
            model.fit(X_poly, y_train)
            
            y_pred = model.predict(X_poly)
            r2 = r2_score(y_train, y_pred)
            rmse = np.sqrt(mean_squared_error(y_train, y_pred))
            mae = mean_absolute_error(y_train, y_pred)
            
            results.append({
                'degree': degree,
                'r2': r2,
                'rmse': rmse,
                'mae': mae,
                'model': model,
                'poly_features': poly_features
            })
            
            if r2 > best_score:
                best_score = r2
                self.best_model = model
                self.best_degree = degree
                self.best_poly_features = poly_features
        
        return results
    
    def predict_future(self, months_ahead: int = 3) -> Dict:
        """Прогноз на будущие периоды с валидацией"""
        if not self.best_model:
            results = self.find_best_model()
            for res in results:
                logger.info(
                    f"Степень {res['degree']}: "
                    f"R²={res['r2']:.3f}, RMSE={res['rmse']:.2f}"
                )
        
        # Подготовка данных для прогноза
        last_month = len(self.df) - 1
        future_months = np.array(range(last_month + 1, last_month + months_ahead + 1))
        X_future = future_months.reshape(-1, 1)
        X_future_poly = self.best_poly_features.transform(X_future)
        
        # Получаем начальный прогноз
        raw_predictions = self.best_model.predict(X_future_poly)
        
        # Валидируем прогноз
        last_actual_value = self.df['total_sum'].iloc[-1]
        validated_predictions = self._validate_prediction(raw_predictions, last_actual_value)
        
        # Получаем фактические данные за последние месяцы
        last_actual = self.df['total_sum'].iloc[-months_ahead:].to_dict()
        
        return {
            'predictions': validated_predictions,
            'raw_predictions': raw_predictions,
            'best_degree': self.best_degree,
            'best_r2': r2_score(
                self.df['total_sum'].values,
                self.best_model.predict(
                    self.best_poly_features.transform(
                        self.df['months'].values.reshape(-1, 1)
                    )
                )
            ),
            'last_actual': last_actual,
            'constraints': {
                'min_value': self.min_value,
                'max_monthly_change': self.max_monthly_change
            }
        }