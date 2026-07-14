# ozon/services/ozon_client.py

import os
from typing import Optional, Dict, Any
import requests
import pandas as pd
from io import StringIO, BytesIO
from datetime import datetime, timedelta

import logging

logger = logging.getLogger(__name__)

class OzonClient:
    DEFAULT_TIMEOUT = 30
    def __init__(self):
        self.api_key = os.getenv('OZON_API_KEY')
        self.client_id = os.getenv('OZON_CLIENT_ID')
        self.ad_client_id = os.getenv('OZON_AD_CLIENT_ID')
        self.ad_client_secret = os.getenv('OZON_AD_CLIENT_SECRET')
        
        if not all([self.api_key, self.client_id, self.ad_client_id, self.ad_client_secret]):
            raise ValueError("Missing required Ozon API credentials")

    def get_access_token(self) -> Optional[str]:
        """Получение токена для рекламного API"""
        url = "https://api-performance.ozon.ru/api/client/token"
        payload = {
            "client_id": self.ad_client_id,
            "client_secret": self.ad_client_secret,
            "grant_type": "client_credentials"
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.DEFAULT_TIMEOUT)
            response.raise_for_status()
            return response.json()['access_token']
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error при получении токена: {e}")
            logger.info(f"Response: {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request Error при получении токена: {e}")
            return None

    def get_advertising_data(self, year: int) -> Optional[Dict[str, Any]]:
        """Получение данных по рекламе"""
        try:
            token = self.get_access_token()
            if not token:
                return {
                    'status': 'error',
                    'message': 'Failed to get access token'
                }

            url = "https://api-performance.ozon.ru/api/client/statistics/expense"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            start_date = f"{year}-01-01"
            end_date = f"{year + 1}-01-01"
            
            params = {
                "dateFrom": start_date,
                "dateTo": end_date
            }
            
            try:
                response = requests.get(url, headers=headers, params=params, timeout=self.DEFAULT_TIMEOUT)
                
                # Если получили ответ не 2xx
                if not response.ok:
                    return {
                        'status': 'error',
                        'message': f'API returned status code {response.status_code}'
                    }
                
                # Проверяем, что ответ не пустой
                if not response.text.strip():
                    return {
                        'status': 'success',
                        'data': [],
                        'metadata': {
                            'year': year,
                            'total_rows': 0,
                            'total_expense': 0,
                            'total_bonus_expense': 0
                        }
                    }
                
                # Пробуем распарсить CSV
                try:
                    df = pd.read_csv(StringIO(response.text), sep=';', decimal=',')
                except Exception as e:
                    return {
                        'status': 'error',
                        'message': f'Failed to parse CSV data: {str(e)}'
                    }

                # Проверяем наличие необходимых колонок
                required_columns = ['ID', 'Дата', 'Название', 'Расход', 'Расход бонусов']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    return {
                        'status': 'error',
                        'message': f'Missing required columns: {", ".join(missing_columns)}'
                    }

                # Обработка числовых колонок
                for column in ['Расход', 'Расход бонусов']:
                    df[column] = pd.to_numeric(
                        df[column].astype(str).str.replace(',', '.').str.replace(' ', ''),
                        errors='coerce'
                    ).fillna(0)

                # Формируем результат
                result = {
                    'status': 'success',
                    'data': df[required_columns].to_dict('records'),
                    'metadata': {
                        'year': year,
                        'total_rows': len(df),
                        'total_expense': float(df['Расход'].sum()),
                        'total_bonus_expense': float(df['Расход бонусов'].sum())
                    }
                }

                return result

            except requests.exceptions.RequestException as e:
                return {
                    'status': 'error',
                    'message': f'Request failed: {str(e)}'
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Unexpected error: {str(e)}'
            }
            
    def get_advertising_data_by_date_range(self, start_date, end_date):
        """Получение данных по рекламе за указанный период"""
        try:
            token = self.get_access_token()
            if not token:
                return {
                    'status': 'error',
                    'message': 'Failed to get access token'
                }

            url = "https://api-performance.ozon.ru/api/client/statistics/expense"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            params = {
                "dateFrom": start_date.strftime("%Y-%m-%d"),
                "dateTo": end_date.strftime("%Y-%m-%d")
            }
            
            try:
                response = requests.get(url, headers=headers, params=params, timeout=self.DEFAULT_TIMEOUT)
                
                # Если получили ответ не 2xx
                if not response.ok:
                    return {
                        'status': 'error',
                        'message': f'API returned status code {response.status_code}'
                    }
                
                # Проверяем, что ответ не пустой
                if not response.text.strip():
                    return {
                        'status': 'success',
                        'data': [],
                        'metadata': {
                            'total_rows': 0,
                            'total_expense': 0,
                            'total_bonus_expense': 0
                        }
                    }
                
                # Пробуем распарсить CSV
                try:
                    df = pd.read_csv(StringIO(response.text), sep=';', decimal=',')
                except Exception as e:
                    return {
                        'status': 'error',
                        'message': f'Failed to parse CSV data: {str(e)}'
                    }

                # Проверяем наличие необходимых колонок
                required_columns = ['ID', 'Дата', 'Название', 'Расход', 'Расход бонусов']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    return {
                        'status': 'error',
                        'message': f'Missing required columns: {", ".join(missing_columns)}'
                    }

                # Обработка числовых колонок
                for column in ['Расход', 'Расход бонусов']:
                    df[column] = pd.to_numeric(
                        df[column].astype(str).str.replace(',', '.').str.replace(' ', ''),
                        errors='coerce'
                    ).fillna(0)

                # Формируем результат
                result = {
                    'status': 'success',
                    'data': df[required_columns].to_dict('records'),
                    'metadata': {
                        'total_rows': len(df),
                        'total_expense': float(df['Расход'].sum()),
                        'total_bonus_expense': float(df['Расход бонусов'].sum())
                    }
                }

                return result

            except requests.exceptions.RequestException as e:
                return {
                    'status': 'error',
                    'message': f'Request failed: {str(e)}'
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'Unexpected error: {str(e)}'
            }
            
    def get_sales_data(self, year: int) -> Optional[Dict[str, Any]]:
        """Получение данных по продажам"""
        url = "https://api-seller.ozon.ru/v3/posting/fbs/list"
        headers = {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        try:
            all_data = []
            start_date = datetime(year, 1, 1)
            end_date = datetime(year + 1, 1, 1)
            
            while start_date < end_date:
                next_date = min(start_date + timedelta(days=31), end_date)
                
                payload = {
                    "dir": "desc",
                    "filter": {
                        "since": start_date.strftime('%Y-%m-%dT%XZ'),
                        "to": next_date.strftime('%Y-%m-%dT%XZ')
                    },
                    "limit": 1000,
                    "offset": 0,
                    "with": {
                        "analytics_data": True,
                        "financial_data": True
                    }
                }
                
                try:
                    while True:
                        response = requests.post(url, headers=headers, json=payload, timeout=30)
                        response.raise_for_status()
                        result = response.json()
                        
                        logger.debug(f"Got response: {str(result)[:200]}")
                        
                        all_data.extend(result["result"]["postings"])
                        
                        if not result["result"]["has_next"]:
                            break
                        payload["offset"] += 1000
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request Error: {e}")
                    return None
                    
                start_date = next_date

            # Преобразуем данные в DataFrame
            df = pd.DataFrame(all_data)
            
            logger.debug(f"Raw DataFrame columns: {df.columns.tolist()}")
            
            # Нормализуем данные из поля 'products'
            if not df.empty and 'products' in df.columns:
                normalized_products = pd.json_normalize(df['products'].apply(lambda x: x[0] if x else {}))
                df = pd.concat([df.drop('products', axis=1), normalized_products], axis=1)
            
            # Выбираем нужные колонки
            selected_columns = [
                'posting_number', 'status', 'in_process_at', 'shipment_date',
                'price', 'offer_id', 'name', 'sku', 'quantity'
            ]
            
            # Проверяем наличие всех необходимых колонок
            missing_columns = [col for col in selected_columns if col not in df.columns]
            if missing_columns:
                logger.warning(f"Missing columns: {missing_columns}")
                return None
                
            df = df[selected_columns]

            # Преобразуем числовые колонки корректно
            numeric_columns = ['price', 'quantity']
            for col in numeric_columns:
                if col in df.columns:
                    try:
                        df[col] = pd.to_numeric(df[col].astype(str).str.split('.').str[0], errors='coerce').fillna(0)
                    except Exception as e:
                        logger.error(f"Error converting column {col}: {e}")
                        logger.debug(f"Sample values: {df[col].head()}")

            logger.debug("Processed DataFrame: %s rows, columns: %s", len(df), df.columns.tolist())

            result = {
                'status': 'success',
                'data': df.to_dict('records'),
                'metadata': {
                    'year': year,
                    'total_rows': len(df),
                    'columns': list(df.columns),
                    'total_orders': len(df),
                    'total_quantity': int(df['quantity'].sum()),
                    'total_price': float(df['price'].sum())
                }
            }

            return result

        except Exception as e:
            logger.error(f"Error in get_sales_data: {e}")
            logger.error(f"Full error details: {str(e)}")
            return None
    
    def get_sales_data_by_date_range(self, start_date, end_date):
        """Получение данных по продажам за указанный период"""
        url = "https://api-seller.ozon.ru/v3/posting/fbs/list"
        headers = {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        try:
            all_data = []
            current_date = start_date
            
            while current_date < end_date:
                next_date = min(current_date + timedelta(days=31), end_date)
                
                payload = {
                    "dir": "desc",
                    "filter": {
                        "since": current_date.strftime('%Y-%m-%dT%XZ'),
                        "to": next_date.strftime('%Y-%m-%dT%XZ')
                    },
                    "limit": 1000,
                    "offset": 0,
                    "with": {
                        "analytics_data": True,
                        "financial_data": True
                    }
                }
                
                try:
                    while True:
                        response = requests.post(url, headers=headers, json=payload, timeout=30)
                        response.raise_for_status()
                        result = response.json()
                        
                        all_data.extend(result["result"]["postings"])
                        
                        if not result["result"]["has_next"]:
                            break
                        payload["offset"] += 1000
                    
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request Error: {e}")
                    
                current_date = next_date

            # Преобразуем данные в DataFrame
            df = pd.DataFrame(all_data)
            
            # Нормализуем данные из поля 'products'
            if not df.empty and 'products' in df.columns:
                normalized_products = pd.json_normalize(df['products'].apply(lambda x: x[0] if x else {}))
                df = pd.concat([df.drop('products', axis=1), normalized_products], axis=1)
            
            # Выбираем нужные колонки
            selected_columns = [
                'posting_number', 'status', 'in_process_at', 'shipment_date',
                'price', 'offer_id', 'name', 'sku', 'quantity'
            ]
            
            # Проверяем наличие колонок
            missing_columns = [col for col in selected_columns if col not in df.columns]
            if missing_columns:
                logger.warning(f"Missing columns: {missing_columns}")
                if df.empty:
                    return None
                # Если какие-то колонки отсутствуют, используем только имеющиеся
                present_columns = [col for col in selected_columns if col in df.columns]
                df = df[present_columns]
            else:
                df = df[selected_columns]

            # Преобразуем числовые колонки
            numeric_columns = ['price', 'quantity']
            for col in numeric_columns:
                if col in df.columns:
                    try:
                        df[col] = pd.to_numeric(df[col].astype(str).str.split('.').str[0], errors='coerce').fillna(0)
                    except Exception as e:
                        logger.error(f"Error converting column {col}: {e}")

            result = {
                'status': 'success',
                'data': df.to_dict('records'),
                'metadata': {
                    'total_rows': len(df),
                    'columns': list(df.columns),
                    'total_orders': len(df),
                    'total_quantity': int(df['quantity'].sum()) if 'quantity' in df.columns else 0,
                    'total_price': float(df['price'].sum()) if 'price' in df.columns else 0
                }
            }

            return result

        except Exception as e:
            logger.error(f"Error in get_sales_data_by_date_range: {e}")
            return None

    def export_advertising_data_to_excel(self, year: int) -> Optional[bytes]:
        """Экспорт рекламных данных в Excel"""
        try:
            result = self.get_advertising_data(year)
            if not result or 'data' not in result or not result['data']:
                logger.warning("No data available for export")
                return None
                
            df = pd.DataFrame(result['data'])
            if df.empty:
                logger.warning("DataFrame is empty")
                return None

            logger.debug("DataFrame before export: %s rows, columns: %s", len(df), df.columns.tolist())

            # Создаем bytes buffer вместо StringIO
            output = BytesIO()
            
            # Сохраняем DataFrame в Excel
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
                
            # Возвращаем bytes
            output.seek(0)
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error in export_advertising_data_to_excel: {e}")
            logger.error(f"Full error details: {str(e)}")
            return None
    
    def export_advertising_data_by_date_range(self, start_date, end_date):
        """Экспорт рекламных данных в Excel за указанный период"""
        try:
            result = self.get_advertising_data_by_date_range(start_date, end_date)
            if not result or 'data' not in result or not result['data']:
                logger.warning("No data available for export")
                return None
                
            df = pd.DataFrame(result['data'])
            if df.empty:
                logger.warning("DataFrame is empty")
                return None

            # Создаем bytes buffer
            output = BytesIO()
            
            # Сохраняем DataFrame в Excel
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
                
            # Возвращаем bytes
            output.seek(0)
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error in export_advertising_data_by_date_range: {e}")
            return None
    
    def export_sales_data_to_excel(self, year: int) -> Optional[bytes]:
        """Экспорт данных по продажам в Excel"""
        try:
            result = self.get_sales_data(year)
            if not result or 'data' not in result or not result['data']:
                logger.warning("No data available for export")
                return None
                
            df = pd.DataFrame(result['data'])
            if df.empty:
                logger.warning("DataFrame is empty")
                return None

            logger.debug("DataFrame before export: %s rows, columns: %s", len(df), df.columns.tolist())

            # Создаем bytes buffer
            output = BytesIO()
            
            # Сохраняем DataFrame в Excel
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
                
            # Возвращаем bytes
            output.seek(0)
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Ошибка при создании Excel файла: {e}")
            logger.error(f"Полные детали ошибки: {str(e)}")
            return None
            
    def export_sales_data_by_date_range(self, start_date, end_date):
        """Экспорт данных по продажам в Excel за указанный период"""
        try:
            result = self.get_sales_data_by_date_range(start_date, end_date)
            if not result or 'data' not in result or not result['data']:
                logger.warning("No data available for export")
                return None
                
            df = pd.DataFrame(result['data'])
            if df.empty:
                logger.warning("DataFrame is empty")
                return None

            # Создаем bytes buffer
            output = BytesIO()
            
            # Сохраняем DataFrame в Excel
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
                
            # Возвращаем bytes
            output.seek(0)
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Ошибка при создании Excel файла: {e}")
            return None