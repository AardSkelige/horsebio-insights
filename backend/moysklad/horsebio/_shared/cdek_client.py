#!/usr/bin/env python3
"""
Клиент API СДЭК v2 (клиентский протокол интеграции с логистикой).

Покрывает ровно то, что нужно демону формирования накладных:
- OAuth-авторизацию (client_credentials) с кэшем токена в памяти;
- создание заказа (POST /v2/orders) и опрос его статуса (GET /v2/orders/{uuid});
- формирование печатной формы-квитанции (POST /v2/print/orders), опрос её
  готовности и скачивание PDF (GET /v2/print/orders/{uuid}.pdf).

Создание заказа и печатной формы у СДЭК — асинхронные: POST возвращает 202 и
uuid сущности, а реальный результат (номер СДЭК, готовый PDF) появляется позже.
Поэтому здесь есть хелперы poll_order / poll_waybill с ожиданием готовности.

Ключи берутся из backend/.env: CDEK_CLIENT_ID, CDEK_CLIENT_SECRET, CDEK_ENV
(test → api.edu.cdek.ru, prod → api.cdek.ru).

Документация-источник: openapi_api_v2_integration.json (в корне репозитория на
время интеграции).
"""

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / '.env')

CDEK_CLIENT_ID = os.getenv('CDEK_CLIENT_ID')
CDEK_CLIENT_SECRET = os.getenv('CDEK_CLIENT_SECRET')
CDEK_ENV = (os.getenv('CDEK_ENV') or 'test').strip().lower()

# Боевая и тестовая среды СДЭК. По умолчанию — тестовая (безопасно).
CDEK_BASE_URLS = {
    'test': 'https://api.edu.cdek.ru',
    'prod': 'https://api.cdek.ru',
}


class CdekError(Exception):
    """Ошибка запроса к СДЭК — текст содержит код/описание из ответа API."""


class CdekClient:
    """HTTP-клиент СДЭК v2 с кэшем OAuth-токена в памяти."""

    def __init__(self, client_id: str = None, client_secret: str = None, env: str = None):
        self.client_id = client_id or CDEK_CLIENT_ID
        self.client_secret = client_secret or CDEK_CLIENT_SECRET
        env = (env or CDEK_ENV or 'test').lower()
        if env not in CDEK_BASE_URLS:
            raise ValueError(f"CDEK_ENV должен быть test или prod, получено: {env!r}")
        self.env = env
        self.base_url = CDEK_BASE_URLS[env]

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "CDEK_CLIENT_ID / CDEK_CLIENT_SECRET не заданы в backend/.env"
            )

        self._token = None
        self._token_expires_at = 0.0  # unixtime, до которого токен валиден

    # ─── Авторизация ────────────────────────────────────────────────────────

    def _authenticate(self) -> None:
        """Получить OAuth-токен (client_credentials) и запомнить его срок жизни.

        Токен обновляем чуть заранее (за 60 с до истечения), чтобы не словить
        401 на границе срока во время длинной серии запросов."""
        url = f"{self.base_url}/v2/oauth/token"
        # СДЭК принимает параметры авторизации как application/x-www-form-urlencoded
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        resp = requests.post(url, data=data, timeout=15)
        if not resp.ok:
            raise CdekError(f"Авторизация СДЭК не удалась: {resp.status_code} {resp.text}")
        payload = resp.json()
        self._token = payload.get("access_token")
        if not self._token:
            raise CdekError(f"Ответ авторизации без access_token: {payload}")
        expires_in = int(payload.get("expires_in") or 3600)
        self._token_expires_at = time.time() + expires_in - 60

    def _ensure_token(self) -> str:
        if not self._token or time.time() >= self._token_expires_at:
            self._authenticate()
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._ensure_token()}",
            "Content-Type": "application/json",
        }

    # ─── Базовые запросы ────────────────────────────────────────────────────

    def _request(self, method: str, path: str, *, params=None, json=None) -> requests.Response:
        url = f"{self.base_url}{path}"
        resp = requests.request(
            method, url, headers=self._headers(), params=params, json=json, timeout=30
        )
        if not resp.ok:
            raise CdekError(f"СДЭК {method} {path}: {resp.status_code} {resp.text}")
        return resp

    def _get(self, path: str, params: dict = None) -> dict:
        return self._request("GET", path, params=params).json()

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, json=body).json()

    # ─── Расчёт стоимости ────────────────────────────────────────────────────

    def get_city_code(self, city_name: str) -> int | None:
        """Код города СДЭК по названию (GET /v2/location/cities?city=...).

        Возвращает code первого совпадения (СДЭК ранжирует по релевантности) или
        None, если город не найден. Код нужен для калькулятора тарифов."""
        rows = self._get("/v2/location/cities", {"city": city_name, "size": 1})
        if isinstance(rows, list) and rows:
            return rows[0].get("code")
        return None

    def calculate_tarifflist(self, from_code: int, to_code: int, packages: list[dict]) -> dict:
        """POST /v2/calculator/tarifflist — все доступные тарифы для направления.

        packages: [{"weight": г, "length": см, "width": см, "height": см}, ...].
        Ответ: {"tariff_codes": [{tariff_code, tariff_name, delivery_sum,
        period_min, period_max, ...}]}."""
        body = {
            "from_location": {"code": from_code},
            "to_location": {"code": to_code},
            "packages": packages,
        }
        return self._post("/v2/calculator/tarifflist", body)

    # ─── Заказы ─────────────────────────────────────────────────────────────

    def create_order(self, order: dict) -> dict:
        """POST /v2/orders. Возвращает тело ответа (202) с entity.uuid и requests[].

        Заказ обрабатывается асинхронно — фактический номер СДЭК появится позже,
        см. poll_order()."""
        return self._post("/v2/orders", order)

    def get_order(self, uuid: str) -> dict:
        """GET /v2/orders/{uuid} — текущее состояние заказа и его запросов."""
        return self._get(f"/v2/orders/{uuid}")

    def find_order_by_number(self, im_number: str) -> dict | None:
        """GET /v2/orders?im_number=... — найти ранее созданный заказ по нашему
        номеру. Защита от дублей: если прошлый прогон успел создать заказ, но
        упал до прикрепления PDF, повторный прогон подхватит его, а не создаст
        второй (СДЭК запрещает дубликаты активного номера в рамках договора).
        Возвращает None, если заказа с таким номером нет."""
        try:
            resp = self._get("/v2/orders", {"im_number": im_number})
        except CdekError:
            return None
        entity = resp.get("entity") if isinstance(resp, dict) else None
        return resp if entity and entity.get("uuid") else None

    def poll_order(self, uuid: str, attempts: int = 10, delay: float = 2.0) -> dict:
        """Дождаться, пока запрос CREATE перейдёт в финальное состояние.

        Возвращает полный ответ get_order. Бросает CdekError, если создание
        завершилось с ошибкой (state=INVALID) или не успело за отведённое время."""
        last = None
        for _ in range(attempts):
            last = self.get_order(uuid)
            create_states = [
                r.get("state")
                for r in last.get("requests", [])
                if r.get("type") == "CREATE"
            ]
            if any(s == "INVALID" for s in create_states):
                errors = [r.get("errors") for r in last.get("requests", []) if r.get("errors")]
                raise CdekError(f"СДЭК отклонил заказ {uuid}: {errors}")
            entity = last.get("entity") or {}
            if entity.get("cdek_number") and all(
                s in ("SUCCESSFUL", "PROCESSING", None) for s in create_states
            ) and any(s == "SUCCESSFUL" for s in create_states):
                return last
            time.sleep(delay)
        raise CdekError(f"Заказ {uuid} не подтверждён СДЭК за {attempts} попыток; последний ответ: {last}")

    # ─── Печатная форма (квитанция) ─────────────────────────────────────────

    @staticmethod
    def _order_ref(order_uuid: str = None, cdek_number: str = None) -> dict:
        """Ссылка на заказ для печатных форм: по uuid ИЛИ по номеру СДЭК."""
        if order_uuid:
            return {"order_uuid": order_uuid}
        if cdek_number:
            return {"cdek_number": str(cdek_number)}
        raise CdekError("нужен order_uuid или cdek_number")

    def create_waybill(self, order_uuid: str = None, copy_count: int = 2, cdek_number: str = None) -> dict:
        """POST /v2/print/orders — заказать формирование квитанции по заказу
        (по uuid или по номеру СДЭК). Возвращает ответ с uuid печатной формы."""
        body = {"orders": [self._order_ref(order_uuid, cdek_number)], "copy_count": copy_count}
        return self._post("/v2/print/orders", body)

    def poll_waybill(self, uuid: str, attempts: int = 10, delay: float = 2.0) -> dict:
        """Дождаться готовности печатной формы (GET /v2/print/orders/{uuid})."""
        last = None
        for _ in range(attempts):
            last = self._get(f"/v2/print/orders/{uuid}")
            entity = last.get("entity") or {}
            statuses = [s.get("code") for s in entity.get("statuses", [])]
            if "READY" in statuses:
                return last
            if "INVALID" in statuses:
                raise CdekError(f"Печатная форма {uuid} отклонена: {last}")
            time.sleep(delay)
        raise CdekError(f"Печатная форма {uuid} не готова за {attempts} попыток; последний ответ: {last}")

    def download_waybill_pdf(self, uuid: str) -> bytes:
        """GET /v2/print/orders/{uuid}.pdf — забрать готовый PDF (байты)."""
        url = f"{self.base_url}/v2/print/orders/{uuid}.pdf"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if not resp.ok:
            raise CdekError(f"Скачивание PDF {uuid}: {resp.status_code} {resp.text}")
        return resp.content

    # ─── ШК места (штрихкод) ─────────────────────────────────────────────────
    # Отдельная печатная форма от накладной: POST /v2/print/barcodes → опрос
    # готовности → скачивание PDF. Формат листа: A4/A5/A6/A7 (по умолчанию A6 —
    # так просил пользователь).

    def create_barcode(self, order_uuid: str = None, fmt: str = "A6", copy_count: int = 1,
                        cdek_number: str = None) -> dict:
        """POST /v2/print/barcodes — заказать формирование ШК места по заказу
        (по uuid или по номеру СДЭК). Возвращает ответ с uuid печатной формы."""
        body = {"orders": [self._order_ref(order_uuid, cdek_number)], "copy_count": copy_count, "format": fmt}
        return self._post("/v2/print/barcodes", body)

    def poll_barcode(self, uuid: str, attempts: int = 10, delay: float = 2.0) -> dict:
        """Дождаться готовности ШК места (GET /v2/print/barcodes/{uuid})."""
        last = None
        for _ in range(attempts):
            last = self._get(f"/v2/print/barcodes/{uuid}")
            entity = last.get("entity") or {}
            statuses = [s.get("code") for s in entity.get("statuses", [])]
            if "READY" in statuses:
                return last
            if "INVALID" in statuses:
                raise CdekError(f"ШК места {uuid} отклонён: {last}")
            time.sleep(delay)
        raise CdekError(f"ШК места {uuid} не готов за {attempts} попыток; последний ответ: {last}")

    def download_barcode_pdf(self, uuid: str) -> bytes:
        """GET /v2/print/barcodes/{uuid}.pdf — забрать готовый PDF ШК места (байты)."""
        url = f"{self.base_url}/v2/print/barcodes/{uuid}.pdf"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if not resp.ok:
            raise CdekError(f"Скачивание ШК {uuid}: {resp.status_code} {resp.text}")
        return resp.content


if __name__ == "__main__":
    # Быстрая проверка авторизации: python3 cdek_client.py
    client = CdekClient()
    print(f"Среда СДЭК: {client.env} ({client.base_url})")
    try:
        token = client._ensure_token()
        print(f"OK: токен получен, длина {len(token)}, живёт до "
              f"{time.strftime('%H:%M:%S', time.localtime(client._token_expires_at))}")
    except CdekError as e:
        print(f"ОШИБКА: {e}")
