#!/usr/bin/env python3
"""
Общая библиотека для работы с API МойСклад — StarPony.

Содержит:
- Токен и базовые настройки
- Класс MoySkladClient с методами _get, _post, _put, _get_all_pages
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[3]
load_dotenv(_BACKEND_DIR / '.env')

# backend/ в пути — отсюда берётся msapi, общий на скрипты и Django.
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from msapi import http as ms_http  # noqa: E402

MOYSKLAD_TOKEN = os.getenv('STARPONY_MOYSKLAD_TOKEN')
if not MOYSKLAD_TOKEN:
    raise ValueError("STARPONY_MOYSKLAD_TOKEN environment variable is required")
BASE_URL = "https://api.moysklad.ru/api/remap/1.2"

HEADERS = {
    "Authorization": f"Bearer {MOYSKLAD_TOKEN}",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
}

DELAY = 0.2  # секунд между запросами


class MoySkladClient:

    def __init__(self, token: str = MOYSKLAD_TOKEN):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/json",
        }

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        resp = ms_http.get(f"{BASE_URL}{endpoint}", headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, data: Any) -> Any:
        resp = ms_http.post(f"{BASE_URL}{endpoint}", headers=self.headers, json=data)
        if not resp.ok:
            print(f"  Ошибка {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()

    def _put(self, endpoint: str, data: Dict) -> Dict:
        resp = ms_http.put(f"{BASE_URL}{endpoint}", headers=self.headers, json=data)
        if not resp.ok:
            print(f"  Ошибка {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()

    def _get_all_pages(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        all_items = []
        offset = 0
        limit = 1000
        while True:
            p = (params or {}).copy()
            p["limit"] = limit
            p["offset"] = offset
            result = self._get(endpoint, p)
            rows = result.get("rows", [])
            all_items.extend(rows)
            if len(rows) < limit:
                break
            offset += limit
            time.sleep(DELAY)
        return all_items

    def get_default_organization(self) -> Dict:
        result = self._get("/entity/organization", {"limit": 1})
        rows = result.get("rows", [])
        if rows:
            return rows[0]
        raise Exception("Организация не найдена")
