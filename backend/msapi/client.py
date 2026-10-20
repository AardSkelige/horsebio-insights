import os

from msapi import http

BASE_URL = 'https://api.moysklad.ru/api/remap/1.2'


def headers():
    return {'Authorization': f"Bearer {os.getenv('MOYSKLAD_TOKEN')}", 'Accept-Encoding': 'gzip'}


def get_json(path, params=None):
    response = http.get(path if path.startswith('http') else f'{BASE_URL}{path}', headers=headers(), params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def post_json(path, payload):
    response = http.post(f'{BASE_URL}{path}', headers=headers(), json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def delete(path):
    http.delete(f'{BASE_URL}{path}', headers=headers(), timeout=60).raise_for_status()
