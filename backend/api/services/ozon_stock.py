"""Остатки FBS на Ozon: сколько товара площадка считает доступным.

Ozon и МойСклад друг о друге не знают: встроенная интеграция везёт к нам заказы,
но остаток на витрине ведёт сама площадка, и до 07.09.2026 его правили руками.
Из-за этого уценка продавалась на Ozon в отрыве от склада: остаток на витрине
жил своей жизнью, заказы приходили на товар, которого уже нет.

Здесь — только запись остатка, ровно то, чего не хватает. Цены, карточки и
заказы Ozon ведёт по-прежнему сам.

Авторизация — Client-Id/Api-Key, как в ozon/services/ozon_client.py (в
ozon_logistics свой клиент на OAuth, для Ozon Доставки; общего у них только хост).

Важное про схемы: FBS — это склад продавца, FBO — склад Ozon. Остатки FBO
площадка считает сама, и этот модуль их не трогает физически: он пишет остаток
на наш собственный склад FBS, а туда попадают только уценённые карточки.
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api-seller.ozon.ru"
TIMEOUT = 30

# За один запрос Ozon принимает 100 пар «товар — склад»
BATCH = 100


class OzonStockError(Exception):
    """Ozon не ответил или отказался принимать остатки."""


def _headers():
    client_id = os.getenv("OZON_CLIENT_ID")
    api_key = os.getenv("OZON_API_KEY")
    if not client_id or not api_key:
        raise OzonStockError("Не заданы OZON_CLIENT_ID / OZON_API_KEY в окружении")
    return {"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json"}


def _post(path, payload):
    try:
        response = requests.post(f"{BASE_URL}{path}", headers=_headers(), json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise OzonStockError(f"Ozon недоступен ({path}): {exc}")
    if response.status_code >= 300:
        raise OzonStockError(f"Ozon ответил {response.status_code} на {path}: {response.text[:300]}")
    return response.json()


def warehouse_id():
    """Идентификатор нашего склада FBS.

    Не константа: id склада — это данные аккаунта, а не код. Складов в списке
    несколько, но живой один — остальные отключены (rFBS для ЕАЭС, тестовые).
    Если однажды активных станет два, молча выбирать первый нельзя: остаток
    уедет не туда, поэтому падаем с внятным текстом.
    """
    data = _post("/v2/warehouse/list", {"limit": 200})
    active = [
        w for w in data.get("warehouses", [])
        if w.get("warehouse_type") == "fbs" and w.get("status") == "created"
    ]
    if not active:
        raise OzonStockError("У продавца нет активного склада FBS — остатки отправлять некуда")
    if len(active) > 1:
        names = ", ".join(f"{w.get('name')} ({w.get('warehouse_id')})" for w in active)
        raise OzonStockError(f"Активных складов FBS несколько ({names}) — нужно выбрать явно")
    return active[0]["warehouse_id"]


def known_offers(offer_ids):
    """Какие из наших артикулов вообще заведены на Ozon.

    Остаток по незаведённому артикулу — не ошибка, а нормальное состояние:
    на сайте позиций уценки больше, чем на Ozon. Отправлять их бессмысленно,
    Ozon вернёт на каждую ошибку.
    """
    offer_ids = list(offer_ids)
    if not offer_ids:
        return set()
    found = set()
    for start in range(0, len(offer_ids), 1000):  # фильтр принимает до 1000 идентификаторов
        data = _post("/v3/product/list", {"filter": {"offer_id": offer_ids[start:start + 1000]}, "limit": 1000})
        found |= {item["offer_id"] for item in data.get("result", {}).get("items", [])}
    return found


def push_stock(items, warehouse):
    """Записать остатки: items — [{'offer_id': ..., 'stock': int}].

    Ozon ждёт количество без учёта своих резервов — он вычитает их сам, поэтому
    отправляем то, что реально доступно к продаже.

    Возвращает список отказов [(offer_id, текст)]: частичный отказ здесь обычное
    дело (карточка в архиве, товар ещё не прошёл модерацию), и ронять из-за одной
    позиции всю синхронизацию нельзя.
    """
    failures = []
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        data = _post("/v2/products/stocks", {
            "stocks": [
                {"offer_id": item["offer_id"], "stock": item["stock"], "warehouse_id": warehouse}
                for item in chunk
            ],
        })
        for row in data.get("result", []):
            if row.get("updated"):
                continue
            errors = "; ".join(
                f"{e.get('code')}: {e.get('message')}" for e in row.get("errors") or []
            ) or "Ozon не обновил остаток и не объяснил почему"
            failures.append((row.get("offer_id"), errors))
    if failures:
        logger.warning("Ozon не принял остатки по %s позициям: %s", len(failures), failures)
    return failures
