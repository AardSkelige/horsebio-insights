"""
Уценка — что лежит на складе уценённого товара и что с ним пора делать.

Уценяем только по одной причине — подходит срок годности. Правила (Лиля, Катя):
уценка при остатке срока 4 месяца, снятие с продажи при остатке 2 месяца,
цена — 70 % от розничной цены сайта.

Срок годности партии МойСклад не хранит, поэтому дату «годен до» проставляет
человек в карточке уценённого товара — доп. поле «Годен до». От неё и считается
всё остальное: сколько дней осталось и пора ли снимать позицию с продажи.

Источник — три запроса к МойСклад: карточки из группы «Товары/Уценка» (там же
доп. поле и цены), остатки по складу «Уценка» и себестоимость из того же отчёта.
Отчёт по документам (дни на складе) дёргается только для позиций с остатком —
их единицы, а запрос идёт по одному товару за раз.
"""

import logging
from datetime import date, datetime
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from api.exceptions import ExternalServiceError
from api.services import site_exchange
from msapi import http as ms_http
from sync.moysklad import MoySkladAPIClient

logger = logging.getLogger(__name__)

BASE_URL = MoySkladAPIClient.BASE_URL

# Склад и группа ищутся по имени: id разные в проде и в тестовом аккаунте,
# а имена стабильны и видны пользователю (тот же приём, что в fbo_stock).
STORE_NAME = "Уценка"
FOLDER_NAME = "Уценка"
FOLDER_PARENT = "Товары"
ATTRIBUTE_NAME = "Годен до"
RETAIL_PRICE_NAME = "Розница – ИП (Сайт | РРЦ)"

# Правила уценки — согласованы 21.08.2026. Держим здесь, а не в настройках:
# меняются раз в год, и в коде их видно рядом с расчётом.
DISCOUNT_RATE = 0.30          # скидка от розничной цены сайта
MONTHS_TO_DELIST = 2          # за сколько месяцев до конца срока снимаем с продажи
DAYS_TO_DELIST = MONTHS_TO_DELIST * 30

REFS_CACHE_KEY = "discounted_refs"
REFS_CACHE_TTL = 24 * 60 * 60

DATA_CACHE_KEY = "discounted_report"
DATA_CACHE_TTL = 5 * 60

PAGE_LIMIT = 1000

# Состояния позиции — порядок важен, он же порядок сортировки на странице
STATE_EXPIRED = "expired"       # срок вышел
STATE_DELIST = "delist"         # пора снимать с продажи
STATE_NO_DATE = "no_date"       # не проставлен «Годен до»
STATE_OK = "ok"


@lru_cache(maxsize=1)
def _headers():
    return MoySkladAPIClient(settings.MOYSKLAD_TOKEN).headers


def _get(path, params=None):
    response = ms_http.get(f"{BASE_URL}{path}", headers=_headers(), params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def _get_all_pages(path, params=None):
    params = dict(params or {})
    params["limit"] = PAGE_LIMIT
    rows = []
    offset = 0
    while True:
        params["offset"] = offset
        payload = _get(path, params)
        page = payload.get("rows", [])
        rows.extend(page)
        offset += PAGE_LIMIT
        total = payload.get("meta", {}).get("size", float("inf"))
        if len(page) < PAGE_LIMIT or offset >= total:
            return rows


def _resolve_refs():
    """href склада «Уценка», href группы «Товары/Уценка» и id доп. поля «Годен до»."""
    cached = cache.get(REFS_CACHE_KEY)
    if cached:
        return cached

    stores = _get("/entity/store", {"filter": f"name={STORE_NAME}", "limit": 1}).get("rows", [])
    if not stores:
        raise ExternalServiceError(f"Склад «{STORE_NAME}» не найден в МойСклад")

    # Имя группы уникально только внутри родителя: «Уценка» лежит в «Товары»
    folders = _get("/entity/productfolder", {"filter": f"name={FOLDER_NAME}", "limit": 10}).get("rows", [])
    folder = next((f for f in folders if f.get("pathName") == FOLDER_PARENT), None)
    if not folder:
        raise ExternalServiceError(f"Группа товаров «{FOLDER_PARENT}/{FOLDER_NAME}» не найдена в МойСклад")

    attributes = _get("/entity/product/metadata/attributes").get("rows", [])
    attribute = next((a for a in attributes if a["name"].strip() == ATTRIBUTE_NAME), None)
    if not attribute:
        raise ExternalServiceError(f"Доп. поле товара «{ATTRIBUTE_NAME}» не заведено в МойСклад")

    refs = (stores[0]["meta"]["href"], folder["meta"]["href"], attribute["id"])
    cache.set(REFS_CACHE_KEY, refs, REFS_CACHE_TTL)
    return refs


def _parse_expiry(value):
    """«Годен до» приходит из МойСклад строкой вида '2026-12-31 00:00:00.000'."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        logger.warning("Не разобрал «%s» = %r", ATTRIBUTE_NAME, value)
        return None


def _price_of(product, name):
    for entry in product.get("salePrices") or []:
        if (entry.get("priceType") or {}).get("name") == name:
            return (entry.get("value") or 0) / 100
    return 0.0


def _state_of(expires, days_left):
    if expires is None:
        return STATE_NO_DATE
    if days_left < 0:
        return STATE_EXPIRED
    if days_left <= DAYS_TO_DELIST:
        return STATE_DELIST
    return STATE_OK


def _days_on_stock(product_id):
    """Сколько дней партии лежат на складе — считает сам МойСклад (avgStockDays).

    Отчёт умеет фильтровать только по одной номенклатуре за раз, поэтому дёргаем
    его лишь для позиций с остатком: их единицы. Ошибка отчёта не должна ронять
    всю страницу — тогда просто не показываем эту колонку у строки.
    """
    try:
        rows = _get(
            "/report/byoperations/stock",
            {"filter": f"assortment={BASE_URL}/entity/product/{product_id}"},
        ).get("rows", [])
    except Exception:
        logger.warning("Отчёт по документам недоступен для товара %s", product_id, exc_info=True)
        return None
    days = [r.get("avgStockDays") for r in rows if (r.get("stock") or 0) > 0 and r.get("avgStockDays")]
    return round(max(days)) if days else None


def _build_data():
    """Собрать отчёт из МойСклад. Тяжёлая часть — кешируется вызывающим."""
    store_href, folder_href, attribute_id = _resolve_refs()
    today = date.today()

    # Карточки ищем по пути группы, а не по ссылке на неё: /entity/product не знает
    # поля фильтрации productFolder и отвечает на него 412 «неизвестное поле».
    products = _get_all_pages("/entity/product", {"filter": f"pathName={FOLDER_PARENT}/{FOLDER_NAME}"})
    by_id = {p["id"]: p for p in products}

    # А вот отчёт по остаткам productFolder как раз понимает. groupBy=product нужен,
    # чтобы в строке пришла ссылка на товар: по умолчанию отчёт группирует по
    # модификациям, и тогда id из href не совпал бы с id карточки.
    stock_rows = _get_all_pages(
        "/report/stock/all",
        {
            "filter": f"store={store_href};productFolder={folder_href};withSubFolders=true",
            "groupBy": "product",
        },
    )
    stock = {}
    for row in stock_rows:
        href = (row.get("meta") or {}).get("href", "")
        product_id = href.rsplit("/", 1)[-1].split("?")[0]
        stock[product_id] = {
            "quantity": row.get("stock") or 0,
            "reserve": row.get("reserve") or 0,
            "cost": (row.get("price") or 0) / 100,
        }

    positions = []
    for product_id, product in by_id.items():
        held = stock.get(product_id, {})
        quantity = held.get("quantity", 0)

        raw_expiry = next(
            (a.get("value") for a in (product.get("attributes") or []) if a.get("id") == attribute_id),
            None,
        )
        expires = _parse_expiry(raw_expiry)
        days_left = (expires - today).days if expires else None

        retail = _price_of(product, RETAIL_PRICE_NAME)
        cost = held.get("cost", 0)

        positions.append({
            "id": product_id,
            "article": product.get("article") or "",
            "name": product.get("name") or "",
            "expires": expires.isoformat() if expires else None,
            "days_left": days_left,
            "state": _state_of(expires, days_left if days_left is not None else 0),
            "quantity": quantity,
            "reserve": held.get("reserve", 0),
            "price": round(retail, 2),
            "price_full": round(retail / (1 - DISCOUNT_RATE), 2) if retail else 0.0,
            "cost": round(cost, 2),
            "sum": round(retail * quantity, 2),
            "sum_cost": round(cost * quantity, 2),
            "days_on_stock": _days_on_stock(product_id) if quantity > 0 else None,
            "ms_url": f"https://online.moysklad.ru/app/#good/edit?id={product_id}",
        })

    # Сначала то, с чем надо что-то делать: истёкшие, потом «пора снимать»,
    # потом позиции без даты, потом остальные — внутри по возрастанию запаса.
    order = {STATE_EXPIRED: 0, STATE_DELIST: 1, STATE_NO_DATE: 2, STATE_OK: 3}
    positions.sort(key=lambda p: (order[p["state"]], p["days_left"] if p["days_left"] is not None else 10**6))

    in_stock = [p for p in positions if p["quantity"] > 0]
    summary = {
        "positions": len(in_stock),
        "units": sum(p["quantity"] for p in in_stock),
        "sum": round(sum(p["sum"] for p in in_stock), 2),
        "sum_cost": round(sum(p["sum_cost"] for p in in_stock), 2),
        "needs_action": sum(1 for p in in_stock if p["state"] in (STATE_EXPIRED, STATE_DELIST, STATE_NO_DATE)),
    }

    return {
        "positions": positions,
        "summary": summary,
        "rules": {
            "discount_rate": DISCOUNT_RATE,
            "months_to_delist": MONTHS_TO_DELIST,
        },
        "site_admin_url": settings.SITE_ADMIN_URL,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@api_view(["GET"])
def discounted_list(request):
    """Позиции на складе «Уценка» с расчётом, что пора снимать с продажи."""
    if request.GET.get("refresh") == "1":
        cache.delete(DATA_CACHE_KEY)

    data = cache.get(DATA_CACHE_KEY)
    if data is None:
        data = _build_data()
        cache.set(DATA_CACHE_KEY, data, DATA_CACHE_TTL)
    return Response(data)


@api_view(["POST"])
def discounted_delist(request, product_id):
    """Снять позицию с продажи на сайте — обменом, без захода в админку.

    Артикул и название берём из МойСклад, а не из тела запроса: страница могла
    открыться час назад, и данные в ней успели устареть.
    """
    try:
        product = _get(f"/entity/product/{product_id}")
    except Exception as exc:
        logger.warning("Товар %s не найден в МойСклад", product_id, exc_info=True)
        raise ExternalServiceError(f"Товар не найден в МойСклад: {exc}")

    site_exchange.set_visibility(
        product_id=product_id,
        article=product.get("article") or "",
        name=product.get("name") or "",
        visibility=site_exchange.HIDDEN_404,
    )

    # Список считается из остатков и дат, а не из доступности на сайте, поэтому
    # кеш сбрасываем только чтобы страница перерисовалась свежей.
    cache.delete(DATA_CACHE_KEY)
    return Response({"ok": True, "product_id": product_id}, status=status.HTTP_200_OK)
