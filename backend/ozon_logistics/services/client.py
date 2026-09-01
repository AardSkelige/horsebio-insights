"""HTTP-клиент Seller API для Ozon Доставки.

Отдельный от ozon/services/ozon_client.py сознательно: там авторизация по
Client-Id/Api-Key и Performance API, здесь — OAuth-токен приложения. Общего,
кроме хоста, у них нет.
"""

import logging
import re

import requests

from ozon_logistics.services import oauth

logger = logging.getLogger(__name__)

BASE_URL = 'https://api-seller.ozon.ru'
DEFAULT_TIMEOUT = 30


def normalize_phone(phone):
    """Приводит телефон к формату Ozon: только цифры, 10-15 знаков.

    В заказы сайта номер попадает как угодно: «+7 (916) 622-90-30», «8916…».
    Ozon Доставка работает только по России, поэтому ведущая восьмёрка в
    одиннадцатизначном номере — это код страны 7, а не часть абонентского номера.
    """
    digits = re.sub(r'\D', '', phone or '')
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    if len(digits) == 10:  # номер без кода страны
        digits = '7' + digits
    if not 10 <= len(digits) <= 15:
        raise OzonLogisticsError(
            f'Телефон «{phone}» не приводится к формату Ozon (нужно 10-15 цифр)'
        )
    return digits


def _checkout_item(item):
    """Позиция для checkout: ровно один идентификатор товара.

    Ozon отвергает запрос с обоими сразу — «either sku or offer_id should be
    specified for each item». Предпочитаем sku: он числовой и однозначный,
    offer_id остаётся запасным вариантом.
    """
    quantity = int(item['quantity'])
    sku = item.get('sku')
    if sku:
        return {'sku': int(sku), 'quantity': quantity}
    offer_id = item.get('offer_id')
    if not offer_id:
        raise OzonLogisticsError('У позиции нет ни sku, ни offer_id')
    return {'offer_id': str(offer_id), 'quantity': quantity}


class OzonLogisticsError(RuntimeError):
    """Seller API ответил ошибкой."""

    def __init__(self, message, *, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class OzonLogisticsTimeout(OzonLogisticsError):
    """Ответ не получен. Для читающих методов — просто ошибка, но для создающих
    означает неизвестный исход: запрос мог дойти и выполниться."""


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
        except requests.Timeout as exc:
            raise OzonLogisticsTimeout(f'Seller API не ответил вовремя: {exc}') from exc
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
        """Доступна ли покупателю доставка Ozon: {'is_possible': bool}.

        Первый шаг оформления по документации и самый безобидный вызов из
        скоупа ozon-logistics: ничего не создаёт и не меняет. Ограничения по
        сумме, категории и географии метод не учитывает.
        """
        return self.request('/v1/delivery/check', {'client_phone': normalize_phone(phone)})

    def point_list(self):
        """Координаты ВСЕХ точек самовывоза: {'points': [{coordinate, map_point_id}]}.

        Ответ не постраничный и может быть большим, поэтому документация советует
        кешировать его у себя, а не дёргать на каждое открытие корзины.
        """
        return self.request('/v1/delivery/point/list', {})

    def point_info(self, map_point_ids):
        """Подробности точек: адрес, часы работы, рейтинг. Не больше 100 за раз."""
        ids = [str(i) for i in map_point_ids]
        if not 0 < len(ids) <= 100:
            raise OzonLogisticsError('Нужно от 1 до 100 идентификаторов точек')
        return self.request('/v1/delivery/point/info', {'map_point_ids': ids})

    def warehouse_list(self, *, limit=200, cursor=None):
        """Склады FBS и rFBS: {'warehouses': [...], 'cursor': ..., 'has_next': ...}.

        Нужен `warehouse_id` нашего склада — с ним товары уезжают в checkout.
        Склады FBO живут отдельно, в /v1/warehouse/fbo/list.
        """
        payload = {'limit': limit}
        if cursor:
            payload['cursor'] = cursor
        return self.request('/v2/warehouse/list', payload)

    def product_list(self, *, limit=100, last_id=None, offer_ids=None):
        """Товары с их `offer_id`, `sku` и признаком остатков FBS.

        `sku` обязателен для checkout и создания заказа, а получить его больше
        негде — в МойСклад его нет.
        """
        payload = {'limit': limit, 'filter': {}}
        if offer_ids:
            payload['filter']['offer_id'] = [str(o) for o in offer_ids]
        if last_id:
            payload['last_id'] = last_id
        return self.request('/v3/product/list', payload)

    def checkout(self, *, phone, items, map_point_id=None, coordinates=None,
                 delivery_schema='MIX'):
        """Варианты доставки, сроки и стоимость логистики для набора товаров.

        Ровно один из `map_point_id` (самовывоз) и `coordinates` (курьер, пара
        широта-долгота). В ответе `splits` — разбиение по складам: у каждого
        свои сроки (`delivery_method.timeslots`) и комиссия (`commissions.total`).
        Недоступность объясняется в `unavailable_reason`.
        """
        if (map_point_id is None) == (coordinates is None):
            raise OzonLogisticsError(
                'Укажите либо map_point_id (самовывоз), либо coordinates (курьер)'
            )
        if not items:
            raise OzonLogisticsError('Список товаров пуст')

        if map_point_id is not None:
            delivery_type = {'pick_up': {'map_point_id': int(map_point_id)}}
        else:
            delivery_type = {'courier': {'coordinates': {
                'latitude': coordinates[0], 'longitude': coordinates[1],
            }}}

        return self.request('/v2/delivery/checkout', {
            'buyer_phone': normalize_phone(phone),
            'delivery_schema': delivery_schema,
            'delivery_type': delivery_type,
            'items': [_checkout_item(item) for item in items],
        })

    def order_create(self, payload):
        """Создаёт заказ в Ozon. Вызывать только после подтверждения оплаты.

        Состав заказа после создания изменить нельзя, а успешный ответ не
        гарантирует, что заказ собрался: часть товаров может не подобраться.
        """
        return self.request('/v2/order/create', payload)

    def posting_fbs_list(self, *, order_numbers=None, since=None, to=None,
                         limit=100, cursor=None):
        """Отправления FBS. Фильтр по номерам заказов — то, что нам и нужно.

        Метод v4: v3 отключён с 31.08.2026.
        """
        filters = {}
        if order_numbers:
            filters['order_numbers'] = [str(n) for n in order_numbers]
        if since:
            filters['since'] = since
        if to:
            filters['to'] = to

        payload = {'filter': filters, 'limit': limit}
        if cursor:
            payload['cursor'] = cursor
        return self.request('/v4/posting/fbs/list', payload)

    def posting_fbo_list(self, *, posting_numbers=None, since=None, to=None,
                         limit=100, cursor=None):
        """Отправления FBO. Здесь фильтр по номерам отправлений, а не заказов.

        Метод v3: v2 отключён с 31.08.2026.
        """
        filters = {}
        if posting_numbers:
            filters['posting_numbers'] = [str(n) for n in posting_numbers]
        if since:
            filters['since'] = since
        if to:
            filters['to'] = to

        payload = {'filter': filters, 'limit': limit}
        if cursor:
            payload['cursor'] = cursor
        return self.request('/v3/posting/fbo/list', payload)

    def returns_list(self, *, limit=100, last_id=None):
        """Возвраты FBO и FBS: невыкупы и возвраты после получения."""
        payload = {'limit': limit}
        if last_id:
            payload['last_id'] = last_id
        return self.request('/v1/returns/list', payload)

    def cancel_reasons_for_order(self, order_number):
        """Причины отмены, допустимые для конкретного заказа: {'reasons': [...]}.

        Документация просит не запрашивать список заранее, «на всякий случай», —
        только когда отмена действительно нужна.
        """
        return self.request('/v1/cancel-reason/list-by-order', {'order_number': str(order_number)})

    def cancel_check(self, order_number):
        """Можно ли отменить заказ: {'cancellable': bool, 'posting_groups': [...]}"""
        return self.request('/v1/order/cancel/check', {'order_number': str(order_number)})

    def cancel_order(self, order_number, *, reason_id, reason_message=''):
        """Отменяет заказ целиком. Процесс асинхронный — исход смотрят в cancel_status."""
        payload = {'order_number': str(order_number), 'reason_id': int(reason_id)}
        if reason_message:
            payload['reason_message'] = reason_message
        return self.request('/v1/order/cancel', payload)

    def cancel_status(self, order_number):
        """Состояние отмены: {'order_number': ..., 'posting_number': [...], 'state': ...}"""
        return self.request('/v1/order/cancel/status', {'order_number': str(order_number)})

    def delivery_map(self, left_bottom, right_top, zoom):
        """Кластеры точек в области карты — для отрисовки при мелком масштабе.

        Координаты — пары (lat, long); zoom от 0 до 19.
        """
        return self.request('/v1/delivery/map', {
            'viewport': {
                'left_bottom': {'lat': left_bottom[0], 'long': left_bottom[1]},
                'right_top': {'lat': right_top[0], 'long': right_top[1]},
            },
            'zoom': zoom,
        })
