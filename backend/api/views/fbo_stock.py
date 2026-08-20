"""
Остатки для FBO — сколько товара можно физически увезти на маркетплейс сегодня.

Зачем отдельная страница. В отчёте «Остатки» МойСклад показывает
    Доступно = Остаток − Резерв + Ожидание,
где «Ожидание» — плановый выпуск по производственным заданиям. Товара ещё нет,
а колонка «Доступно» его уже прибавила: у Пробиотика GastroPro 800 г при остатке
237 и резерве 18 «Доступно» показывает 289, хотя увезти сегодня можно 219.
Вычисляемую колонку в отчёт МойСклад добавить нельзя — поэтому считаем здесь:

    Количество = Остаток − Резерв,   Ожидание показываем отдельно, справочно.

Источник — один запрос /report/stock/all по складу готовой продукции и группе
товаров (без фильтра в отчёт лезут кружки, блокноты и пробники без артикула).
Неснижаемый остаток в отчёт по остаткам не входит, поэтому он берётся вторым
запросом из карточек товаров и показывается справочно: из «Количества» он не
вычитается, но видно, что позиция уже ниже минимума.
"""

import logging
from datetime import datetime
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.exceptions import ExternalServiceError
from api.utils.excel_export import ExcelReportBuilder
from msapi import http as ms_http
from sync.moysklad import MoySkladAPIClient

logger = logging.getLogger(__name__)

BASE_URL = MoySkladAPIClient.BASE_URL

# Склад и группа товаров ищутся по имени: id жёстко зашивать нельзя (они разные
# в проде и в тестовом аккаунте), а имена стабильны и видны пользователю.
STORE_NAME = "Склад готовой продукции"
FOLDER_PATH = "Товары"

# Ссылки на склад/группу меняются раз в жизни — держим сутки.
REFS_CACHE_KEY = "fbo_stock_refs"
REFS_CACHE_TTL = 24 * 60 * 60

# Сам отчёт весит 5 единиц лимита МойСклад — не дёргаем его на каждый F5.
DATA_CACHE_KEY = "fbo_stock_report"
DATA_CACHE_TTL = 5 * 60

PAGE_LIMIT = 1000


@lru_cache(maxsize=1)
def _headers():
    """Заголовки МойСклад — те же, что у общего клиента синхронизации."""
    return MoySkladAPIClient(settings.MOYSKLAD_TOKEN).headers


def _get(path, params=None):
    response = ms_http.get(f"{BASE_URL}{path}", headers=_headers(), params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def _get_all_pages(path, params=None):
    """Все строки эндпоинта с пагинацией по meta.size."""
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
        # size по умолчанию бесконечен: без него неполная страница остаётся
        # единственным признаком конца, иначе отчёт молча обрезался бы до одной страницы
        total = payload.get("meta", {}).get("size", float("inf"))
        if len(page) < PAGE_LIMIT or offset >= total:
            return rows


def _resolve_refs():
    """href склада готовой продукции и группы товаров."""
    cached = cache.get(REFS_CACHE_KEY)
    if cached:
        return cached

    stores = _get("/entity/store", {"filter": f"name={STORE_NAME}", "limit": 1}).get("rows", [])
    if not stores:
        raise ExternalServiceError(f"Склад «{STORE_NAME}» не найден в МойСклад")

    folders = _get("/entity/productfolder", {"filter": f"name={FOLDER_PATH}", "limit": 10}).get("rows", [])
    # Имя группы уникально только внутри родителя — берём корневую (без pathName)
    root = next((f for f in folders if not f.get("pathName")), None)
    if not root:
        raise ExternalServiceError(f"Группа товаров «{FOLDER_PATH}» не найдена в МойСклад")

    refs = (stores[0]["meta"]["href"], root["meta"]["href"])
    cache.set(REFS_CACHE_KEY, refs, REFS_CACHE_TTL)
    return refs


def _in_folder(path_name):
    """Путь ведёт в группу «Товары» — саму или её подгруппу.

    Фильтр pathName~Товары на стороне МойСклад ищет вхождение подстроки, поэтому
    в выдачу попадают ещё и «Товары маркетплейсов», и «Товары на выезд» — у них
    свои минимумы, подмешивать их сюда нельзя.
    """
    path_name = path_name or ""
    return path_name == FOLDER_PATH or path_name.startswith(f"{FOLDER_PATH}/")


def _minimum_balances():
    """{product_id: неснижаемый остаток} по товарам из группы «Товары»."""
    rows = _get_all_pages("/entity/product", {"filter": f"pathName~{FOLDER_PATH}"})
    return {
        row["id"]: float(row["minimumBalance"])
        for row in rows
        if _in_folder(row.get("pathName")) and row.get("minimumBalance")
    }


def _build_data():
    """Собрать отчёт из МойСклад. Тяжёлая часть — кешируется вызывающим."""
    store_href, folder_href = _resolve_refs()
    minimums = _minimum_balances()

    stock_filter = (
        f"store={store_href};"
        f"productFolder={folder_href};withSubFolders=true;"
        "stockMode=all;quantityMode=all"
    )
    # groupBy=product обязателен: по умолчанию отчёт группирует по модификациям,
    # и у товара с модификациями в строке придёт variant-href — минимум из карточки
    # товара по нему не найдётся, и позиция молча покажется «без минимума»
    rows = _get_all_pages("/report/stock/all", {"filter": stock_filter, "groupBy": "product"})

    items = []
    for row in rows:
        product_id = row["meta"]["href"].split("/")[-1].split("?")[0]
        stock = float(row.get("stock") or 0)
        reserve = float(row.get("reserve") or 0)
        in_transit = float(row.get("inTransit") or 0)
        minimum = minimums.get(product_id, 0.0)
        quantity = stock - reserve
        items.append({
            "article": row.get("article") or "",
            "name": row.get("name") or "",
            "code": row.get("code") or "",
            "stock": stock,
            "reserve": reserve,
            "quantity": quantity,
            "in_transit": in_transit,
            "minimum_balance": minimum,
            # Товар кончается: свободного меньше, чем сам же МойСклад считает минимумом
            "below_minimum": bool(minimum) and quantity < minimum,
            "is_empty": not (stock or reserve or in_transit),
        })

    items.sort(key=lambda item: item["name"].lower())

    return {
        "generated_at": timezone.now().isoformat(),
        "store": STORE_NAME,
        "items": items,
    }


def _get_data(force_refresh=False):
    if not force_refresh:
        cached = cache.get(DATA_CACHE_KEY)
        if cached:
            return cached
    try:
        data = _build_data()
    except ExternalServiceError:
        raise
    except Exception as exc:
        logger.error("Остатки для FBO: не удалось получить данные из МойСклад: %s", exc)
        raise ExternalServiceError("Не удалось получить остатки из МойСклад")
    cache.set(DATA_CACHE_KEY, data, DATA_CACHE_TTL)
    return data


@api_view(['GET'])
def fbo_stock(request):
    """Остатки для FBO. ?refresh=1 — мимо кеша, свежий запрос в МойСклад."""
    force = request.GET.get('refresh') in ('1', 'true')
    return Response({'status': 'success', 'data': _get_data(force_refresh=force)})


@api_view(['GET'])
def fbo_stock_export(request):
    """Выгрузка в Excel: Артикул · Название · Количество · Ожидание."""
    data = _get_data()
    rows = [item for item in data['items'] if not item['is_empty']]

    generated_at = datetime.fromisoformat(data['generated_at'])
    builder = ExcelReportBuilder("Остатки для FBO")
    builder.add_title_row(
        f"Остатки для FBO · {data['store']} · на {timezone.localtime(generated_at).strftime('%d.%m.%Y %H:%M')}",
        merge_cols=4,
    )
    builder.add_headers(['Артикул', 'Название', 'Количество', 'Ожидание'])
    for item in rows:
        builder.add_row([item['article'], item['name'], item['quantity'], item['in_transit']])
    builder.set_column_widths([18, 60, 14, 14])

    filename = f"fbo-stock-{timezone.localtime(generated_at).strftime('%Y-%m-%d')}.xlsx"
    return builder.to_http_response(filename)
