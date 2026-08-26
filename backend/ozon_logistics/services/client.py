"""HTTP-клиент Seller API для Ozon Доставки.

Отдельный от ozon/services/ozon_client.py сознательно: там авторизация по
Client-Id/Api-Key и Performance API, здесь — OAuth-токен приложения. Общего,
кроме хоста, у них нет.
"""

import logging

import requests

from ozon_logistics.services import oauth

logger = logging.getLogger(__name__)

BASE_URL = 'https://api-seller.ozon.ru'
DEFAULT_TIMEOUT = 30


class OzonLogisticsError(RuntimeError):
    """Seller API ответил ошибкой."""

    def __init__(self, message, *, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class OzonLogisticsClient:
    """Тонкая обёртка: подставляет Bearer и переживает истёкший токен."""

    def __init__(self, *, timeout=DEFAULT_TIMEOUT):
        self.timeout = timeout

    def _post(self, path, payload=None, *, token):
        url = f'{BASE_URL}{path}'
        try:
            return requests.post(
                url,
                json=payload or {},
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OzonLogisticsError(f'Seller API недоступен: {exc}') from exc

    def request(self, path, payload=None):
        """POST к Seller API с авторизацией.

        На 401 один раз обновляем токен и повторяем: между проверкой срока и
        самим запросом токен мог быть отозван на стороне Ozon.
        """
        response = self._post(path, payload, token=oauth.get_valid_token())

        if response.status_code == 401:
            logger.info('Ozon Доставка: 401 на %s, обновляю токен и повторяю', path)
            response = self._post(path, payload, token=oauth.get_valid_token(force_refresh=True))

        if response.status_code != 200:
            raise OzonLogisticsError(
                f'{path} → HTTP {response.status_code}: {response.text[:500]}',
                status_code=response.status_code,
                payload=response.text,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise OzonLogisticsError(f'{path} вернул не JSON: {response.text[:500]}') from exc

    # --- Методы Ozon Доставки -------------------------------------------------

    def delivery_check(self, phone):
        """Доступна ли покупателю доставка Ozon по его номеру телефона.

        Первый шаг оформления по документации и самый безобидный вызов из
        скоупа ozon-logistics: ничего не создаёт и не меняет.
        """
        return self.request('/v1/delivery/check', {'phone': phone})
