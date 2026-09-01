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
from datetime import date, datetime, timedelta
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from rest_framework.decorators import api_view
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework import status

from api.exceptions import ExternalServiceError
from api.services import site_csv, site_exchange, site_feed
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

SITE_URL = "https://horse-bio.ru"
UC_SUFFIX = "-UC"

# Категория на сайте — покупатель видит именно это название
SITE_FOLDER = "Уцененный товар"

# Текст на карточке уценки — согласован с ГД, менять только вместе с docs/ucenka.md
NOTICE = (
    "<p><strong>Товар реализуется со скидкой в связи с истекающим сроком годности:"
    " от 2 до 4 месяцев на момент покупки.</strong></p>"
    "<p>Пожалуйста, учитывайте, что товары из категории «Уцененный товар»"
    " обмену и возврату не подлежат.</p>"
    "<p>Скидка на уценённый товар не суммируется с другими действующими акциями"
    " и специальными предложениями*.</p>"
    "<p>*Исключением является акция на бесплатную доставку, если она действует"
    " на момент оформления заказа.</p>"
)
ANNOUNCE = (
    "Уценка по сроку годности — скидка 30 %. Срок годности на момент покупки"
    " от 2 до 4 месяцев. Обмену и возврату не подлежит."
)

# Транслитерация под ЧПУ сайта: адрес страницы товара нигде не хранится, поэтому
# и здесь, и в файле импорта он собирается из названия карточки по одному правилу.
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
}

# Правила уценки — согласованы 21.08.2026. Держим здесь, а не в настройках:
# меняются раз в год, и в коде их видно рядом с расчётом.
DISCOUNT_RATE = 0.30          # скидка от розничной цены сайта
MONTHS_TO_DELIST = 2          # за сколько месяцев до конца срока снимаем с продажи
DAYS_TO_DELIST = MONTHS_TO_DELIST * 30

REFS_CACHE_KEY = "discounted_refs"
REFS_CACHE_TTL = 24 * 60 * 60

DATA_CACHE_KEY = "discounted_report"
DATA_CACHE_TTL = 5 * 60

# Позиции без отчётов, которые нужны только самой странице (аналитика за период,
# дни на складе). Их спрашивают уведомления — а их спрашивают из любого раздела,
# поэтому запрос должен быть заметно дешевле открытия страницы.
POSITIONS_CACHE_KEY = "discounted_positions"
POSITIONS_CACHE_TTL = 10 * 60

PAGE_LIMIT = 1000

# За какой период считаем итоги, если период не задан явно
DEFAULT_PERIOD_DAYS = 365

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


def site_slug(name):
    """ЧПУ страницы товара на сайте: «Уценка // Пробиотик, 1600г» → ucenka-probiotik-1600g."""
    letters = []
    for char in name.lower():
        if char in TRANSLIT:
            letters.append(TRANSLIT[char])
        elif char.isalnum() and char.isascii():
            letters.append(char)
        else:
            letters.append("-")
    slug = "".join(letters)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _keywords(name):
    """Ключевые слова для карточки уценки.

    Страница закрыта от индексации, так что поле почти декоративное. Но пустым
    его оставлять нельзя: пустое значение обмен не применяет, и в карточке
    останется то, что лежало там раньше.
    """
    base = name.split("//", 1)[-1].strip().rstrip(".").lower()
    return f"уценка, распродажа, {base}"


def _site_state(product, on_site):
    """Что известно про карточку на сайте: опубликована ли, с какой ценой и остатком.

    on_site is None означает «фид не ответили», и это не то же самое, что «карточки
    нет»: в таком случае published остаётся неизвестным (None), чтобы интерфейс не
    показал «не опубликовано» там, где просто не смогли проверить.
    """
    article = product.get("article") or ""
    name = product.get("name") or ""
    fallback = f"{SITE_URL}/{site_slug(name)}"
    if on_site is None:
        return {"published": None, "site_url": fallback, "site_price": None, "site_quantity": None}

    offer = on_site.get(article)
    if not offer:
        return {"published": False, "site_url": fallback, "site_price": None, "site_quantity": None}
    return {
        "published": True,
        "site_url": offer.get("url") or fallback,
        "site_price": offer.get("price"),
        "site_quantity": offer.get("amount"),
    }


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


def _build_analytics(store_href, days):
    """Итоги по складу «Уценка» за период: уценено, продано, списано.

    Два отчёта вместо разбора документов:
      • «Обороты» дают приход (это и есть уценённое) и весь расход со склада;
      • «Прибыль по товарам» — сколько из этого расхода ушло продажами, по какой
        цене и с какой себестоимостью.

    Списание считается как остаток: что ушло со склада, но не было продано.
    Возвраты вычитаем из продаж, иначе вернувшийся товар посчитался бы проданным
    дважды — один раз продажей, второй раз попал бы в «списано» с минусом.
    """
    moment_to = datetime.now()
    moment_from = moment_to - timedelta(days=days)
    period = {
        "momentFrom": moment_from.strftime("%Y-%m-%d 00:00:00"),
        "momentTo": moment_to.strftime("%Y-%m-%d %H:%M:%S"),
        "filter": f"store={store_href}",
    }

    turnover = _get_all_pages("/report/turnover/all", period)
    marked_qty = sum((r.get("income") or {}).get("quantity") or 0 for r in turnover)
    marked_cost = sum((r.get("income") or {}).get("sum") or 0 for r in turnover) / 100
    left_qty = sum((r.get("outcome") or {}).get("quantity") or 0 for r in turnover)
    left_cost = sum((r.get("outcome") or {}).get("sum") or 0 for r in turnover) / 100

    profit = _get_all_pages("/report/profit/byproduct", period)
    sold_qty = sum((r.get("sellQuantity") or 0) - (r.get("returnQuantity") or 0) for r in profit)
    revenue = sum((r.get("sellSum") or 0) - (r.get("returnSum") or 0) for r in profit) / 100
    sold_cost = sum((r.get("sellCostSum") or 0) - (r.get("returnCostSum") or 0) for r in profit) / 100

    # Отрицательным быть не должно, но округления двух разных отчётов лучше не
    # выпускать на экран в виде «списано −0.3 шт»
    written_off_qty = max(left_qty - sold_qty, 0)
    written_off_cost = max(left_cost - sold_cost, 0)

    return {
        "period_days": days,
        "period_from": moment_from.date().isoformat(),
        "marked": {"quantity": round(marked_qty, 2), "cost": round(marked_cost, 2)},
        "sold": {"quantity": round(sold_qty, 2), "revenue": round(revenue, 2), "cost": round(sold_cost, 2)},
        "written_off": {"quantity": round(written_off_qty, 2), "cost": round(written_off_cost, 2)},
    }


def _invalidate_cache():
    """Сбросить всё, что посчитано по складу «Уценка».

    Кешей три: страница, облегчённые позиции для уведомлений и сами уведомления.
    Разъехавшись, они показывают в колокольчике то, что человек уже исправил,
    поэтому сбрасываются только вместе.
    """
    cache.delete(DATA_CACHE_KEY)
    cache.delete(POSITIONS_CACHE_KEY)
    # Локальный импорт: пакет уведомлений сам импортирует этот модуль ради
    # провайдера, и на уровне модуля вышел бы круг
    from api.notifications import core as notifications

    notifications.invalidate("discounted")


def _build_positions(refresh=False, with_days_on_stock=True):
    """Позиции склада «Уценка»: остаток, срок, цена и что сейчас на витрине.

    with_days_on_stock=False пропускает отчёт по документам — он идёт по одному
    запросу на товар и нужен только странице, но не уведомлениям.
    """
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

    # Что сейчас выставлено на сайте. Обмен умеет только писать, поэтому факт
    # публикации и витринные цену с остатком читаем из служебного фида.
    try:
        # По «Обновить» перечитываем и фид: иначе страница десять минут показывает
        # «нет на витрине» по карточке, которая уже опубликована
        on_site = site_feed.offers(refresh=refresh)
    except Exception:
        logger.warning("Фид сайта недоступен — публикация позиций неизвестна", exc_info=True)
        on_site = None

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
            "days_on_stock": _days_on_stock(product_id) if with_days_on_stock and quantity > 0 else None,
            # Ссылку для человека МойСклад отдаёт сам в meta.uuidHref: у веб-интерфейса
            # свой идентификатор, и адрес, собранный из id карточки, не открывается.
            "ms_url": (product.get("meta") or {}).get("uuidHref"),
            **_site_state(product, on_site),
        })

    # Сначала то, с чем надо что-то делать: истёкшие, потом «пора снимать»,
    # потом позиции без даты, потом остальные — внутри по возрастанию запаса.
    order = {STATE_EXPIRED: 0, STATE_DELIST: 1, STATE_NO_DATE: 2, STATE_OK: 3}
    positions.sort(key=lambda p: (order[p["state"]], p["days_left"] if p["days_left"] is not None else 10**6))
    return positions


def positions_snapshot(refresh=False):
    """Позиции для тех, кому нужен только их состав — прежде всего уведомлений.

    Если страница уже собрана, берём готовое: это те же самые позиции. Иначе
    считаем облегчённо и кладём в свой кеш с более длинным сроком — уведомления
    опрашиваются чаще, чем открывается раздел.
    """
    if not refresh:
        data = cache.get(DATA_CACHE_KEY)
        if data:
            return data["positions"]
        cached = cache.get(POSITIONS_CACHE_KEY)
        if cached is not None:
            return cached

    positions = _build_positions(refresh=refresh, with_days_on_stock=False)
    cache.set(POSITIONS_CACHE_KEY, positions, POSITIONS_CACHE_TTL)
    return positions


def _build_data(period_days=DEFAULT_PERIOD_DAYS, refresh=False):
    """Собрать отчёт из МойСклад. Тяжёлая часть — кешируется вызывающим."""
    store_href, _, _ = _resolve_refs()
    positions = _build_positions(refresh=refresh)

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
        "analytics": _build_analytics(store_href, period_days),
        "rules": {
            "discount_rate": DISCOUNT_RATE,
            "months_to_delist": MONTHS_TO_DELIST,
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@api_view(["GET"])
def discounted_list(request):
    """Позиции на складе «Уценка» с расчётом, что пора снимать с продажи."""
    refresh = request.GET.get("refresh") == "1"
    if refresh:
        _invalidate_cache()

    data = cache.get(DATA_CACHE_KEY)
    if data is None:
        data = _build_data(refresh=refresh)
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
    _invalidate_cache()
    return Response({"ok": True, "product_id": product_id}, status=status.HTTP_200_OK)


@api_view(["POST"])
def discounted_publish(request, product_id):
    """Завести карточку уценки на сайте: фото, цена, остаток, тексты и SEO.

    Фотографии берём у основной карточки — артикул уценки без суффикса `-UC`.
    Карточка создаётся скрытой: открывает её человек, убедившись, что всё легло
    правильно. Так же безопаснее при повторном вызове — обновление не выкинет
    товар в продажу раньше времени.
    """
    try:
        product = _get(f"/entity/product/{product_id}")
    except Exception as exc:
        logger.warning("Товар %s не найден в МойСклад", product_id, exc_info=True)
        raise ExternalServiceError(f"Товар не найден в МойСклад: {exc}")

    article = product.get("article") or ""
    name = product.get("name") or ""
    price = _price_of(product, RETAIL_PRICE_NAME)
    if not price:
        raise ExternalServiceError(
            f"У карточки не заполнена цена «{RETAIL_PRICE_NAME}» — публиковать нечего"
        )

    store_href, _, _ = _resolve_refs()
    stock_rows = _get_all_pages(
        "/report/stock/all",
        {"filter": f"store={store_href};product={BASE_URL}/entity/product/{product_id}",
         "groupBy": "product"},
    )
    quantity = int(sum(row.get("stock") or 0 for row in stock_rows))

    source_article = article[: -len(UC_SUFFIX)] if article.endswith(UC_SUFFIX) else article
    pictures = site_feed.pictures_for(source_article)

    # Если карточка уже на витрине, доступность не трогаем: иначе повторная
    # отправка (например, чтобы обновить фотографии) снимет товар с продажи.
    on_site = {}
    try:
        on_site = site_feed.offers()
    except Exception:
        logger.warning("Фид сайта недоступен, публикуем карточку скрытой", exc_info=True)
    visibility = None if article in on_site else site_exchange.HIDDEN_404

    uploaded = site_exchange.publish(
        product_id=product_id,
        article=article,
        name=name,
        price=int(round(price)),
        quantity=quantity,
        pictures=pictures,
        visibility=visibility,
        attributes=[
            ("Анонс товара", ANNOUNCE),
            ("Подробное описание товара", NOTICE),
            ("ЧПУ", site_slug(name)),
            ("Заголовок (H1)", name),
            ("Заголовок страницы (Title)", f"{name} — уценка со скидкой 30 % | Horse-Bio"),
            ("Описание страницы (Description)", ANNOUNCE),
            ("Ключевые слова (Keywords)", _keywords(name)),
            # Уценка не должна конкурировать с основной карточкой в поиске
            ("Запретить индексацию страницы", 1),
            # Промокоды на уценённый товар не действуют
            ("Товар уже со скидкой", 1),
        ],
    )

    _invalidate_cache()
    return Response({
        "ok": True,
        "product_id": product_id,
        "pictures": uploaded,
        "quantity": quantity,
        "price": int(round(price)),
    }, status=status.HTTP_200_OK)


def _must_hide(position):
    """Карточку нельзя оставлять на витрине.

    Два случая из регламента: до конца срока осталось меньше двух месяцев
    (продавать нечего — покупателю не хватит срока на курс и доставку) и товар
    раскуплен. Обмен, который снимал бы такие карточки сам, упёрся в демо-лимит,
    поэтому снятие делает тот же файл импорта.
    """
    return position["state"] in (STATE_EXPIRED, STATE_DELIST) or position["quantity"] <= 0


def _csv_row(position, pictures, description="", fields=None):
    """Строка файла импорта по позиции склада «Уценка».

    description — текст основной карточки. Пустой оставляем поле пустым: импорт
    затрёт описание, которое уже стоит в карточке, а восстанавливать его неоткуда.

    fields — дополнительные поля основной карточки (состав, применение,
    противопоказания и прочее). На сайте они обязательные, без них карточку
    не сохранить, а руками это несколько тысяч знаков на позицию.
    """
    name = position["name"]
    return {
        "article": position["article"],
        "name": name,
        "folder": SITE_FOLDER,
        # Скрытой карточка уходит в двух случаях: её ещё нет на витрине (открывает
        # её человек, проверив глазами) или её пора снять — по сроку или потому,
        # что товар кончился. Всё остальное, что уже продаётся, файл не трогает.
        "hidden": 0 if position.get("published") and not _must_hide(position) else 1,
        "price": f"{position['price']:.2f}",
        # Зачёркнутая цена — РРЦ, от которой считали скидку
        "price_old": f"{position['price_full']:.2f}",
        "amount": int(position["quantity"]),
        # Промокоды на уценённый товар не действуют
        "discounted": 1,
        "note": ANNOUNCE,
        "body": (NOTICE + description) if description else "",
        "image": ", ".join(pictures),
        "sef_url": site_slug(name),
        # Уценка не должна конкурировать с основной карточкой в поиске
        "seo_noindex": 1,
        "seo_h1": name,
        "seo_title": f"{name} — уценка со скидкой 30 % | Horse-Bio",
        "seo_description": ANNOUNCE,
        "seo_keywords": _keywords(name),
        **{f"cf_{key}": value for key, value in (fields or {}).items()},
    }


@api_view(["GET"])
def discounted_csv(request):
    """Файл импорта для админки сайта — на случай, когда обмен недоступен.

    Обмен работает в демо-режиме с лимитом на число загруженных предложений;
    когда лимит выбран, он отвечает `success`, но часть полей не применяет.
    Импорт CSV лимитов не имеет, поэтому файл — надёжный запасной путь.

    Файл приводит витрину в соответствие со складом целиком, а не только заводит
    карточки: позиции с остатком получают фактическое количество, а те, что пора
    снять по сроку или раскуплены, — признак «скрыто». Поэтому в него идут ещё и
    опубликованные позиции с нулевым остатком: без них раскупленная карточка
    осталась бы в продаже.

    Если фид сайта не ответил, файл не собирается вовсе. Колонка «Скрыто» считается
    от того, что сейчас на витрине, а при недоступном фиде это неизвестно: карточки
    вышли бы скрытыми все до одной, и импорт снял бы с продажи весь раздел.
    """
    positions = positions_snapshot()
    if any(p.get("published") is None for p in positions):
        raise ExternalServiceError(
            "Фид сайта не ответил — неизвестно, что сейчас на витрине, и файл"
            " снял бы с продажи все карточки. Нажмите «Обновить» и попробуйте снова."
        )

    positions = [p for p in positions if p["quantity"] > 0 or p.get("published")]

    rows = []
    for position in positions:
        article = position["article"]
        source = article[: -len(UC_SUFFIX)] if article.endswith(UC_SUFFIX) else article
        rows.append(_csv_row(
            position,
            site_feed.pictures_for(source),
            site_feed.description_for(source),
            site_feed.rich_fields_for(source),
        ))

    response = HttpResponse(site_csv.build(rows), content_type="text/csv; charset=windows-1251")
    response["Content-Disposition"] = 'attachment; filename="ucenka-import.csv"'
    return response
