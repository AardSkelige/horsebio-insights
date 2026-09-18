"""Тонкий слой к МойСкладу для роботов Ozon Доставки.

Здесь только то, что нужно обоим потребителям — поиску дублей и записи сведений
о доставке в заказ: заголовки, четыре глагола и поиск заказа сайта. Логика
живёт у них, а не тут.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from msapi import http as ms_http

load_dotenv(Path(__file__).resolve().parents[2] / '.env')

BASE = 'https://api.moysklad.ru/api/remap/1.2'


class MoyskladError(RuntimeError):
    """МойСклад недоступен или ответил ошибкой."""


def headers():
    """Собираем на каждый запрос: сменённый токен не должен требовать перезапуска."""
    return {
        'Authorization': f"Bearer {os.getenv('MOYSKLAD_TOKEN')}",
        'Accept-Encoding': 'gzip',
    }


def get(path, params=None):
    try:
        data = ms_http.get(f'{BASE}{path}', headers=headers(), params=params).json()
    except Exception as exc:  # сеть, таймаут, некорректный JSON
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if isinstance(data, dict) and data.get('errors'):
        raise MoyskladError(f'МойСклад вернул ошибку: {data["errors"]}')
    return data


def post(path, payload):
    try:
        data = ms_http.post(f'{BASE}{path}', headers=headers(), json=payload).json()
    except Exception as exc:
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if isinstance(data, dict) and data.get('errors'):
        raise MoyskladError(f'МойСклад отказал в создании: {data["errors"]}')
    return data


def put(path, payload):
    try:
        data = ms_http.put(f'{BASE}{path}', headers=headers(), json=payload).json()
    except Exception as exc:
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if isinstance(data, dict) and data.get('errors'):
        raise MoyskladError(f'МойСклад отказал в изменении: {data["errors"]}')
    return data


def delete(path):
    try:
        response = ms_http.delete(f'{BASE}{path}', headers=headers())
    except Exception as exc:
        raise MoyskladError(f'МойСклад недоступен: {exc}') from exc
    if response.status_code not in (200, 204):
        raise MoyskladError(
            f'МойСклад отказал в удалении ({response.status_code}): {response.text[:300]}'
        )
    return True


def order_by_external_code(external_code, params=None):
    """Наш заказ сайта: демон 06 кладёт номер заказа сайта в externalCode."""
    query = {'filter': f'externalCode={external_code}', 'limit': 1}
    query.update(params or {})
    rows = get('/entity/customerorder', query).get('rows', [])
    return rows[0] if rows else None
