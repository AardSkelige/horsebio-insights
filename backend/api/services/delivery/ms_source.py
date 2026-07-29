"""Доступ к МойСклад для калькулятора доставки: позиции заказа и данные упаковки.

Отдельный тонкий слой (а не общий ProductionHelper) — нужны ровно две вещи:
позиции заказа покупателя и вес+габариты товара. МойСклад троттлит серии
запросов (HTTP 429 отдаётся как JSON без данных), поэтому GET обязательно с
обработкой 429/errors — иначе поля читаются как пустые (см. историю замеров).
"""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")  # backend/.env

_TOKEN = os.getenv("MOYSKLAD_TOKEN")
_BASE = "https://api.moysklad.ru/api/remap/1.2"
_HEADERS = {"Authorization": f"Bearer {_TOKEN}", "Accept-Encoding": "gzip"}

# Кастомные атрибуты карточки товара с габаритами упаковки (см).
_DIM_ATTRS = ("Длина упаковки, см", "Ширина упаковки, см", "Высота упаковки, см")

# Эвристика распознавания «ведра 5,8 л» по объёму карточки (см³). Требует
# уточнения у отдела упаковки — точного признака в МойСклад пока нет.
_BUCKET_VOLUME_RANGE = (5000, 7000)


class MoyskladError(Exception):
    pass


def _get(url: str, params: dict | None = None) -> dict:
    """GET с ретраем на сеть и на троттлинг (429 / тело с errors)."""
    last = None
    for attempt in range(6):
        try:
            r = requests.get(url, headers=_HEADERS, params=params, timeout=60)
            if r.status_code == 429:
                time.sleep(1.5 * (attempt + 1)); continue
            data = r.json()
            if isinstance(data, dict) and data.get("errors"):
                last = data["errors"]
                time.sleep(1.5 * (attempt + 1)); continue
            return data
        except requests.RequestException as e:
            last = str(e)
            time.sleep(1.5 * (attempt + 1))
    raise MoyskladError(f"МойСклад недоступен: {last}")


def find_order(number_or_id: str) -> dict | None:
    """Заказ покупателя по номеру (name) или по id, с раскрытыми позициями."""
    val = (number_or_id or "").strip()
    if not val:
        return None
    expand = "positions.assortment,salesChannel"
    # по внутреннему id (uuid)
    if len(val) >= 32 and "-" in val:
        try:
            return _get(f"{_BASE}/entity/customerorder/{val}", {"expand": expand})
        except MoyskladError:
            return None
    # Номер заказа. В учёте упаковки его пишут без ведущего нуля («3453»), а в
    # МойСклад он хранится дополненным («03453») — пробуем оба варианта.
    # Номера НЕ уникальны (повторяются между годами: 03453 в 2024/25/26), но
    # нумерация сбрасывается ежегодно, поэтому окно 1 мес + свежий заказ снимает
    # неоднозначность: считать доставку старых заказов смысла нет.
    since = (datetime.now() - timedelta(days=31)).strftime("%Y-%m-%d 00:00:00")
    candidates = [val]
    if val.isdigit():
        candidates += [z for z in (val.zfill(5), val.zfill(6)) if z != val]
    for name in candidates:
        res = _get(f"{_BASE}/entity/customerorder",
                   {"filter": f"name={name};moment>={since}",
                    "expand": expand, "order": "moment,desc", "limit": 1})
        rows = res.get("rows") or []
        if rows:
            return rows[0]
    return None


def marketplace_channel(order: dict) -> str | None:
    """Название канала продаж, если заказ маркетплейсный (type=MARKETPLACE),
    иначе None. Доставку маркетплейсных заказов считает площадка — их исключаем."""
    channel = order.get("salesChannel") or {}
    if channel.get("type") == "MARKETPLACE":
        return channel.get("name")
    return None


# Компоненты адреса, которые точно НЕ являются городом (улица/дом/индекс/район/
# область/пометки про пункты ТК). shipmentAddress — свободный текст менеджера
# («Пункт Сдэк: … обл., … район., п. Кузьмоловский, ул. …»), поэтому эвристика
# грубая: город лишь ПРЕДЗАПОЛНЯЕТ поле, оператор подтверждает по заметке.
_NOT_CITY = ("ул", "пр-т", "пр.", "просп", "д.", "дом", "пер", "ш.", "шоссе",
             "обл", "область", "район", "р-н", "край", "пункт", "терминал",
             "кв", "стр", "корп", "сдэк", "пэк", "байкал")
_COUNTRY_NAMES = {"россия", "российская федерация", "рф"}


def _normalize_city_part(part: str) -> str:
    """Убирает служебный префикс населённого пункта: «г Москва» → «Москва»."""
    value = part.strip(" .")
    low = value.lower()
    for prefix in ("город ", "г. ", "г "):
        if low.startswith(prefix):
            return value[len(prefix):].strip(" .")
    return value


def extract_city(order: dict) -> str | None:
    """Best-effort город получателя из shipmentAddress (только предзаполнение).

    Берём первую строку (там обычно основной адрес), часть до скобки, режем по
    запятым и возвращаем первый кириллический компонент без стоп-слов. Не
    полагаемся на результат — оператор правит, глядя на shipment_note()."""
    first_line = (order.get("shipmentAddress") or "").split("\n")[0]
    raw = first_line.split("(")[0]
    for raw_part in raw.split(","):
        part = _normalize_city_part(raw_part)
        if not part or part.isdigit():
            continue
        if not any(ch.lower() in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя" for ch in part):
            continue  # латинские коды ПВЗ (VLD2) — не город
        low = part.lower()
        if low in _COUNTRY_NAMES:
            continue
        if any(low == w or low.startswith(w + " ") or f" {w}" in low or f" {w}." in low for w in _NOT_CITY):
            continue
        if ":" in part:  # «Пункт Сдэк: Ленинградская обл.» — пометка, не город
            continue
        return part
    return None


def shipment_note(order: dict) -> str:
    """Сырой текст адреса/заметок из заказа — показываем оператору как справку
    (там реальные пункты выдачи ТК, записанные менеджером)."""
    return (order.get("shipmentAddress") or "").strip()


def recent_orders(limit: int = 10) -> list[dict]:
    """Последние заказы покупателей (не маркетплейсные) для выбора в один клик.

    [{id, name, counterparty, city, sum, moment}]. Тянем с запасом, т.к. часть
    отсеиваем как маркетплейсную."""
    # ВАЖНО: МойСклад игнорирует expand при limit>100, поэтому идём страницами
    # по 100 с expand agent/salesChannel. Своих (не-МП) заказов в топе мало —
    # маркетплейсных много, поэтому просматриваем несколько страниц.
    out = []
    for page in range(6):  # до 600 заказов — с запасом на МП-шум
        res = _get(f"{_BASE}/entity/customerorder",
                   {"order": "moment,desc", "limit": 100, "offset": page * 100,
                    "expand": "agent,salesChannel"})
        rows = res.get("rows", [])
        for o in rows:
            if marketplace_channel(o):
                continue
            out.append({
                "id": o.get("id"),
                "name": o.get("name"),
                "counterparty": (o.get("agent") or {}).get("name", ""),
                "city": extract_city(o),        # предзаполнение, оператор правит
                "address": shipment_note(o),    # сырая заметка-справка
                "sum": round((o.get("sum") or 0) / 100, 2),  # МС хранит в копейках
                "moment": o.get("moment"),
            })
            if len(out) >= limit:
                return out
        if len(rows) < 100:
            break
    return out


def order_positions(order: dict) -> list[dict]:
    """[{href, name, code, qty}] по позициям-товарам заказа (услуги пропускаем)."""
    out = []
    for pos in order.get("positions", {}).get("rows", []):
        a = pos.get("assortment") or {}
        if a.get("meta", {}).get("type") not in ("product", "variant"):
            continue
        out.append({
            "href": a["meta"]["href"],
            "name": a.get("name", "?"),
            "code": a.get("code") or "",
            "qty": int(pos.get("quantity") or 0),
        })
    return out


def pack_data(href: str) -> dict:
    """Вес (г), габариты (см) и признак ведра по карточке товара.

    {'weight_g': float|None, 'dims_cm': (l,w,h)|None, 'is_bucket_58': bool}.
    None в weight/dims означает незаполненные данные — повод заблокировать расчёт."""
    card = _get(href)
    attrs = {x["name"]: x.get("value") for x in card.get("attributes", [])}
    weight = card.get("weight") or 0
    dims = [attrs.get(k) for k in _DIM_ATTRS]
    volume = card.get("volume") or 0
    lo, hi = _BUCKET_VOLUME_RANGE
    return {
        "weight_g": float(weight) if weight else None,
        "dims_cm": tuple(float(d) for d in dims) if all(dims) else None,
        "is_bucket_58": lo <= volume <= hi,
    }


def _is_finished_product(product: dict) -> bool:
    """Готовая продукция — товары из папок под корнем «Товары» (ArtroPro, VitaPro
    и т.п.). Сырьё («Материалы для производства»), тара/этикетки/реклама (пустой
    путь) и «Товары маркетплейсов» — исключаем."""
    path = (product.get("productFolder") or {}).get("pathName")
    if path is None:
        return False
    return path == "Товары" or path.startswith("Товары/")


def search_products(query: str, limit: int = 20) -> list[dict]:
    """Поиск ТОЛЬКО готовой продукции для ручного ввода: [{href, name, code}].
    Сырьё, тару и маркетплейсные позиции не показываем — их не отгружают клиенту."""
    res = _get(f"{_BASE}/entity/product",
               {"search": query, "limit": max(limit * 3, 50), "expand": "productFolder"})
    out = []
    for r in res.get("rows", []):
        if not _is_finished_product(r):
            continue
        out.append({"href": r["meta"]["href"], "name": r.get("name", "?"), "code": r.get("code") or ""})
        if len(out) >= limit:
            break
    return out
