"""Оркестратор оценки доставки: позиции → раскладка → тарифы ПЭК и СДЭК.

Два входа (режима ввода): по номеру заказа МойСклад и ручной список позиций.
Оба сводятся к списку (товар, количество), дальше путь общий.

Политика нехватки данных: если хотя бы у одной позиции нет веса или габаритов —
расчёт БЛОКИРУЕТСЯ (цену не показываем), возвращаем список проблемных позиций.
Так решено с заказчиком: лучше честно «не могу», чем занижённая цена-обманка.
"""

from . import cdek_calculator, ms_source, pec_calculator
from .packing import Item, PackResult, pack


def _build_items(positions: list[dict]) -> tuple[list[Item], list[dict]]:
    """positions: [{href, name, code, qty}]. Возвращает (items, missing), где
    missing — позиции без веса/габаритов (с пометкой, чего не хватает)."""
    items: list[Item] = []
    missing: list[dict] = []
    for p in positions:
        data = ms_source.pack_data(p["href"])
        lacks = []
        if not data["weight_g"]:
            lacks.append("вес")
        if not data["dims_cm"]:
            lacks.append("габариты")
        if lacks:
            missing.append({"name": p["name"], "code": p["code"], "lacks": lacks})
            continue
        items.append(Item(
            sku=p["code"], name=p["name"], qty=p["qty"],
            weight_g=data["weight_g"], dims_cm=data["dims_cm"],
            is_bucket_58=data["is_bucket_58"],
        ))
    return items, missing


def _packing_payload(result: PackResult) -> dict:
    """Сводка раскладки для фронта."""
    return {
        "places": result.total_places,
        "weight_kg": round(result.total_weight_g / 1000, 2),
        "volume_l": round(result.total_volume_cm3 / 1000, 1),
        "boxes": result.summary_by_box(),
        "detail": [
            {
                "box": b.box.code,
                "weight_kg": round(b.weight_g / 1000, 2),
                "fill_pct": round(b.used_volume_cm3 / b.box.volume_cm3 * 100),
                "items": [u.name for u in b.units],
            }
            for b in result.boxes
        ],
        "unpackable": [u.name for u in result.unpackable],
    }


def _estimate(positions: list[dict], to_city: str) -> dict:
    """Общее ядро: собрать позиции, при полноте данных — раскладка и тарифы."""
    to_city = (to_city or "").strip()
    if not to_city:
        return {"error": "не указан город назначения"}
    if not positions:
        return {"error": "нет позиций для расчёта"}

    items, missing = _build_items(positions)
    if missing:
        return {"blocked": True, "missing": missing}

    result = pack(items)
    payload = {
        "blocked": False,
        "missing": [],
        "to_city": to_city,
        "packing": _packing_payload(result),
        "carriers": {
            "pec": pec_calculator.calculate(result, to_city),
            "cdek": cdek_calculator.calculate(result, to_city),
        },
    }
    return payload


def estimate_by_order(number_or_id: str, to_city: str) -> dict:
    """Режим «по номеру заказа»: тянем позиции из МойСклад."""
    order = ms_source.find_order(number_or_id)
    if order is None:
        return {"error": f"заказ не найден в МойСклад: {number_or_id!r}"}
    mp = ms_source.marketplace_channel(order)
    if mp:
        return {"error": f"маркетплейсный заказ (канал «{mp}») — доставку считает площадка"}
    # Город берём ТОЛЬКО от оператора: адрес в заказе — свободные заметки про
    # пункты ТК, машинно город не вытащить надёжно. Заметку отдаём для показа.
    note = ms_source.shipment_note(order)
    city = (to_city or "").strip()
    if not city:
        return {"error": "Укажите город получателя", "order": order.get("name"), "address": note}
    positions = ms_source.order_positions(order)
    result = _estimate(positions, city)
    result["order"] = order.get("name")
    result["address"] = note
    return result


def estimate_by_positions(positions: list[dict], to_city: str) -> dict:
    """Режим «ручной ввод»: positions — [{href, qty}] (name/code подтянем)."""
    enriched = []
    for p in positions:
        href = p.get("href")
        qty = int(p.get("qty") or 0)
        if not href or qty <= 0:
            continue
        enriched.append({
            "href": href,
            "name": p.get("name", "?"),
            "code": p.get("code", ""),
            "qty": qty,
        })
    return _estimate(enriched, to_city)
