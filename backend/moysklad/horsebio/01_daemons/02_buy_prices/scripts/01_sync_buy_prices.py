#!/usr/bin/env python3
"""
Синхронизация buyPrice из FIFO-себестоимости МойСклад.

Запускается ежедневно через cron. Сравнивает FIFO-себестоимость
из /report/stock/all с полем buyPrice каждого товара — и обновляет те,
где они расходятся. Дату последнего обновления пишет в доп. поле товара.

История всех запусков хранится в data/.sync_state.json.

Использование:
    cd 01_daemons/02_buy_prices/scripts && python3 01_sync_buy_prices.py
    python3 01_sync_buy_prices.py              # обновление (реальные изменения)
    python3 01_sync_buy_prices.py --dry-run    # только показать что изменится
"""

import sys
import os
import time
import json
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import MOYSKLAD_TOKEN, BASE_URL

HEADERS = {
    "Authorization": f"Bearer {MOYSKLAD_TOKEN}",
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip"
}

DATA_DIR = Path(__file__).parent.parent / "data"
STATE_FILE = DATA_DIR / ".sync_state.json"
DELAY = 0.2  # секунд между запросами обновления
HISTORY_KEEP = 90  # сколько запусков хранить в истории

CUSTOM_FIELD_NAME = 'Дата обновления себестоимости – поле "Закупочная цена" (с накладными)'
MOYSKLAD_WEB = "https://online.moysklad.ru/app"

# Причина изменения себестоимости по типу операции
OP_TYPE_REASON = {
    "productionstagecompletion": "Выпущена новая партия — пересчитана FIFO-себестоимость",
    "processing":   "Тех. операция изменила состав/остатки",
    "enter":        "Ручное оприходование остатков",
    "loss":         "Списание изменило остатки",
    "supply":       "Поступление товара по новой цене",
    "demand":       "Отгрузка изменила остатки",
    "move":         "Перемещение между складами",
    "inventory":    "Коррекция остатков через инвентаризацию",
    "salesreturn":  "Возврат от покупателя",
    "retaildemand": "Розничная продажа изменила остатки",
}

# Человекочитаемые названия типов операций
OP_TYPE_LABEL = {
    "productionstagecompletion": "Производство",
    "processing":   "Тех. операция",
    "enter":        "Оприходование",
    "loss":         "Списание",
    "supply":       "Приёмка",
    "demand":       "Отгрузка",
    "move":         "Перемещение",
    "inventory":    "Инвентаризация",
    "salesreturn":  "Возврат от покупателя",
    "retaildemand": "Розничная продажа",
}

# Соответствие типа операции → путь в веб-интерфейсе МойСклад
OP_TYPE_TO_PATH = {
    "productionstagecompletion": "productionstagecompletion",
    "processing":   "processing",
    "enter":        "enter",
    "loss":         "loss",
    "supply":       "supply",
    "demand":       "demand",
    "move":         "move",
    "inventory":    "inventory",
    "salesreturn":  "salesreturn",
    "retaildemand": "retaildemand",
}


# === State ===

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_run": None, "last_stats": {}, "history": []}


def save_state(state: dict):
    DATA_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8"
    )


# === API ===

def get_rub_currency_meta() -> dict:
    resp = requests.get(f"{BASE_URL}/entity/currency", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    for c in resp.json().get("rows", []):
        if c.get("default"):
            return c["meta"]
    raise RuntimeError("Дефолтная валюта не найдена")


def get_all_pages(endpoint: str, params: dict = None) -> list[dict]:
    all_rows = []
    offset = 0
    limit = 1000
    while True:
        p = (params or {}).copy()
        p["limit"] = limit
        p["offset"] = offset
        resp = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=p, timeout=60)
        resp.raise_for_status()
        rows = resp.json().get("rows", [])
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
        time.sleep(DELAY)
    return all_rows


def get_custom_field_meta(field_name: str) -> dict | None:
    """Вернуть meta доп. поля по имени (нужно для обновления через API)."""
    resp = requests.get(f"{BASE_URL}/entity/product/metadata/attributes", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    for attr in resp.json().get("rows", []):
        if attr.get("name") == field_name:
            return attr["meta"]
    return None


def _build_reason(op: dict, old_fifo_rub: float) -> str:
    """Сформировать человекочитаемую причину изменения FIFO-себестоимости."""
    op_type = op.get("op_type", "")
    qty = op.get("quantity", 0) or 0
    batch = op.get("batch_cost_rub")

    qty_str = f"{qty:g} шт" if qty else ""
    batch_str = f"{batch:.2f}р/шт" if batch is not None else ""

    if op_type == "productionstagecompletion":
        if batch is not None and qty:
            direction = "выше" if batch > old_fifo_rub else "ниже"
            return (f"Произведено {qty_str} по {batch_str} — "
                    f"себестоимость партии {direction} текущей FIFO ({old_fifo_rub:.2f}р), FIFO пересчитана")
        return "Выпуск новой партии, FIFO-себестоимость пересчитана"

    if op_type == "supply":
        if batch is not None and qty:
            direction = "выше" if batch > old_fifo_rub else "ниже"
            return (f"Поступило {qty_str} по {batch_str} — "
                    f"цена прихода {direction} текущей FIFO ({old_fifo_rub:.2f}р)")
        return "Поступление товара по новой цене"

    if op_type == "enter":
        if batch is not None and qty:
            return f"Оприходовано {qty_str} по {batch_str}"
        return "Ручное оприходование остатков"

    if op_type == "salesreturn":
        if batch is not None and qty:
            return f"Возврат {qty_str} по {batch_str}"
        return "Возврат от покупателя"

    if op_type == "inventory":
        return "Коррекция остатков через инвентаризацию"

    return OP_TYPE_REASON.get(op_type, "")


def get_last_op_for_product(product_id: str) -> dict | None:
    """
    Найти последнюю операцию, которая повлияла на себестоимость товара.
    Запрашивает report/turnover/byoperations за последние 90 дней по товару.
    Возвращает dict с полями: op_type, doc_name, doc_date, url — или None.

    Почему momentFrom, а не limit+order: API игнорирует order=moment,desc
    и всегда возвращает строки по возрастанию. Малый limit срезал бы только
    старые операции, пропуская свежие (как было с limit=10).
    """
    moment_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d 00:00:00")
    try:
        resp = requests.get(
            f"{BASE_URL}/report/turnover/byoperations",
            headers=HEADERS,
            params={
                "filter": f"product=https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id}",
                "momentFrom": moment_from,
                "limit": 1000,
            },
            timeout=30,
        )
        resp.raise_for_status()
        rows = resp.json().get("rows", [])
        if not rows:
            return None

        # Ищем последнюю ВХОДЯЩУЮ операцию как человекочитаемую причину.
        # Исходящие (demand/loss/retaildemand) тоже влияют на FIFO (сжигают старые партии),
        # но их неудобно показывать как "причину" — они не несут новую цену.
        AVCO_TYPES = {"enter", "supply", "salesreturn", "inventory", "productionstagecompletion"}
        avco_rows = [
            r for r in rows
            if r.get("operation", {}).get("meta", {}).get("type") in AVCO_TYPES
            and (r.get("quantity") or 0) > 0
        ]
        if not avco_rows:
            return None
        row = avco_rows[-1]  # API возвращает строки по возрастанию — берём последнюю (самую свежую)
        op_meta = row.get("operation", {}).get("meta", {})
        op_type = op_meta.get("type", "")
        op_href = op_meta.get("href", "")
        doc_id = op_href.split("/")[-1].split("?")[0] if op_href else ""
        doc_name = row.get("operation", {}).get("name", "")
        doc_date = row.get("operation", {}).get("moment", "")[:10]

        # Себестоимость единицы из строки оборотов
        # cost = себестоимость на единицу в копейках (costSum всегда None в этом отчёте)
        quantity = row.get("quantity", 0) or 0
        unit_cost_kopecks = abs(row.get("cost", 0) or 0)  # уже на единицу, в копейках
        batch_cost_rub = unit_cost_kopecks / 100 if unit_cost_kopecks else None

        web_path = OP_TYPE_TO_PATH.get(op_type, op_type)
        url = f"{MOYSKLAD_WEB}/#{web_path}/edit?id={doc_id}" if doc_id and web_path else ""

        return {
            "op_type": op_type,
            "doc_name": doc_name,
            "doc_date": doc_date,
            "doc_id": doc_id,
            "url": url,
            "quantity": quantity,
            "batch_cost_rub": batch_cost_rub,
        }
    except Exception:
        return None


def update_product_buy_price(product_id: str, price_kopecks: int,
                              currency_meta: dict, attr_meta: dict | None, now_ms: str):
    payload = {
        "buyPrice": {
            "value": price_kopecks,
            "currency": {"meta": currency_meta}
        }
    }
    if attr_meta:
        payload["attributes"] = [{"meta": attr_meta, "value": now_ms}]

    resp = requests.put(
        f"{BASE_URL}/entity/product/{product_id}",
        headers=HEADERS, json=payload, timeout=30
    )
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")


# === Основная логика ===

def _export_results(updated, skipped_same, skipped_zero, errors, path):
    """Структурированный JSON для страницы /checks: стат-карточки + список изменений."""
    import json as _json
    from datetime import datetime as _dt

    stats = [
        {"label": "Обновлено", "value": len(updated), "tone": "ok" if updated else "neutral"},
        {"label": "Уже актуальны", "value": len(skipped_same), "tone": "neutral"},
        {"label": "Себестоимость 0", "value": len(skipped_zero), "tone": "neutral"},
        {"label": "Ошибки", "value": len(errors), "tone": "critical" if errors else "neutral"},
    ]
    categories = []
    if updated:
        items = []
        for c in updated:
            d = c.get("delta_rub", c.get("new_rub", 0) - c.get("old_rub", 0))
            sign = "+" if d > 0 else ""
            cause = c.get("cause") or {}
            tail = f" · {cause.get('label', '')} №{cause.get('doc_name', '')}" if cause.get("doc_name") else ""
            items.append({"key": "", "ms_id": "", "object": c["name"], "severity": "info",
                          "detail": f"{c.get('old_rub', 0):.2f} → {c.get('new_rub', 0):.2f} ₽ ({sign}{d:.2f}){tail}"})
        categories.append({"key": "updated", "title": "Обновлённые закупочные цены", "severity": "info",
                           "kind": None, "ms_type": None, "count": len(items), "items": items})
    if errors:
        categories.append({"key": "errors", "title": "Ошибки", "severity": "critical", "kind": None, "ms_type": None,
                           "count": len(errors),
                           "items": [{"key": "", "ms_id": "", "object": e.get("name", "—"), "severity": "critical",
                                      "detail": e.get("error", "")} for e in errors]})
    payload = {
        "generated_at": _dt.now().isoformat(timespec="seconds"), "params": {},
        "summary": {"critical": len(errors), "important": 0, "warnings": 0, "ok": len(updated), "stats": stats},
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Синхронизация buyPrice из /report/stock/all")
    parser.add_argument("--dry-run", action="store_true",
                        help="Только показать изменения, ничего не менять")
    parser.add_argument("--results-out", type=str, default=None,
                        help="Путь для структурированного JSON находок (для страницы /checks)")
    args = parser.parse_args()

    now = datetime.now()
    now_ms = now.strftime("%Y-%m-%d %H:%M:%S.000")
    ts = now.strftime("%Y-%m-%d %H:%M")

    print("=== Синхронизация закупочных цен ===")
    print(f"Дата: {ts}")
    if args.dry_run:
        print("⚠️  DRY RUN — изменений в МойСклад не будет")
    print()

    state = load_state()
    if state.get("last_run"):
        print(f"Последний запуск: {state['last_run']}")
        last = state.get("last_stats", {})
        if last:
            print(f"  Тогда: обновлено {last.get('updated', 0)}, "
                  f"актуальных {last.get('skipped_same', 0)}, "
                  f"ошибок {last.get('errors', 0)}")
        print()

    # 1. Валюта
    print("1. Получаем валюту (RUB)...")
    currency_meta = get_rub_currency_meta()
    print("   ОК")

    # 2. Доп. поле
    print(f'2. Проверяем доп. поле "{CUSTOM_FIELD_NAME}"...')
    attr_meta = get_custom_field_meta(CUSTOM_FIELD_NAME)
    if attr_meta:
        print(f"   Найдено ✅")
    else:
        print("   Не найдено — дата обновления записываться не будет")

    # 3. Все товары с buyPrice
    print()
    print("3. Загружаем товары из /entity/product...")
    all_products = get_all_pages("/entity/product")
    product_by_id = {p["id"]: p for p in all_products}
    print(f"   Всего товаров: {len(product_by_id)}")

    # 4. Себестоимость из /report/stock/all
    print()
    print("4. Загружаем себестоимость из /report/stock/all...")
    stock_items = get_all_pages("/report/stock/all")
    print(f"   Позиций в отчёте: {len(stock_items)}")

    # href содержит ?expand=supplier — обрезаем query string
    # price в /report/stock/all — FIFO-себестоимость в копейках (взвешенная средняя по текущим партиям)
    stock_price_by_id: dict[str, int] = {}
    for item in stock_items:
        if item.get("meta", {}).get("type") != "product":
            continue
        pid = item["meta"]["href"].split("/")[-1].split("?")[0]
        price_kopecks = round(item.get("price", 0) or 0)
        if price_kopecks > 0:
            stock_price_by_id[pid] = price_kopecks

    print(f"   Товаров с ненулевой себестоимостью: {len(stock_price_by_id)}")

    # 5. Сравниваем и обновляем
    print()
    print("5. Сравниваем и обновляем...")
    print()

    updated = []
    skipped_same = []
    skipped_zero = []
    errors = []

    sorted_ids = sorted(stock_price_by_id.keys(),
                        key=lambda pid: product_by_id.get(pid, {}).get("name", ""))

    for i, pid in enumerate(sorted_ids, 1):
        product = product_by_id.get(pid)
        if not product:
            continue

        name = product.get("name", "—")
        stock_kopecks = stock_price_by_id[pid]
        stock_price_rub = stock_kopecks / 100
        current_kopecks = (product.get("buyPrice") or {}).get("value") or 0
        current_rub = current_kopecks / 100

        if stock_kopecks == current_kopecks:
            skipped_same.append({"name": name, "id": pid, "price_rub": stock_price_rub})
            continue

        delta = stock_price_rub - current_rub
        sign = "+" if delta > 0 else ""

        # Ищем последнюю операцию, изменившую себестоимость
        last_op = get_last_op_for_product(pid)

        # Проверяем совпадает ли направление: если FIFO-себестоимость выросла, операция должна быть
        # по цене выше старой FIFO, и наоборот. Если не совпадает — кто-то исправил
        # старый документ задним числом, и найденная операция тут ни при чём.
        retroactive = False
        if last_op and last_op.get("batch_cost_rub") is not None:
            batch = last_op["batch_cost_rub"]
            direction_ok = (delta > 0 and batch >= current_rub) or \
                           (delta < 0 and batch <= current_rub)
            if not direction_ok:
                retroactive = True

        cause_str = ""
        if last_op and not retroactive:
            label = OP_TYPE_LABEL.get(last_op["op_type"], last_op["op_type"])
            cause_str = f"  ← {label} №{last_op['doc_name']} ({last_op['doc_date']})"

        print(f"  [{i:3d}] {name[:55]:<55}  "
              f"{current_rub:.2f} → {stock_price_rub:.2f} руб  ({sign}{delta:.2f}){cause_str}")
        if retroactive:
            print(f"         Причина: изменён старый документ в истории (какой именно — через API не видно)")
        elif last_op:
            reason = _build_reason(last_op, current_rub)
            if reason:
                print(f"         Причина: {reason}")
            if last_op.get("url"):
                print(f"         {last_op['url']}")

        change = {
            "name": name, "id": pid,
            "old_rub": round(current_rub, 4),
            "new_rub": round(stock_price_rub, 4),
            "delta_rub": round(delta, 4),
        }
        if last_op:
            change["cause"] = {
                "label": OP_TYPE_LABEL.get(last_op["op_type"], last_op["op_type"]),
                "reason": _build_reason(last_op, current_rub),
                "op_type": last_op["op_type"],
                "doc_name": last_op["doc_name"],
                "doc_date": last_op["doc_date"],
                "url": last_op.get("url", ""),
            }

        if args.dry_run:
            updated.append(change)
        else:
            try:
                time.sleep(DELAY)
                update_product_buy_price(pid, stock_kopecks, currency_meta, attr_meta, now_ms)
                print(f"         ✅ обновлено")
                change["updated_at"] = ts
                updated.append(change)
            except Exception as e:
                print(f"         ❌ {e}")
                errors.append({"name": name, "id": pid, "error": str(e)})

    # Товары с нулевой себестоимостью
    for item in stock_items:
        if item.get("meta", {}).get("type") != "product":
            continue
        pid = item["meta"]["href"].split("/")[-1].split("?")[0]
        if not item.get("price", 0):
            name = product_by_id.get(pid, {}).get("name", "—")
            skipped_zero.append({"name": name, "id": pid})

    # 6. Итог
    print()
    print("=" * 65)
    action = "Будет обновлено" if args.dry_run else "Обновлено"
    print(f"ИТОГ:")
    print(f"  {action}:                {len(updated)}")
    print(f"  Уже актуальные:          {len(skipped_same)}")
    print(f"  Себестоимость 0 (пропущено): {len(skipped_zero)}")
    if errors:
        print(f"  Ошибки:                  {len(errors)}")
    print("=" * 65)

    if args.results_out:
        try:
            _export_results(updated, skipped_same, skipped_zero, errors, args.results_out)
        except Exception as e:
            print(f"Ошибка сохранения результатов JSON: {e}")

    # 7. Сохраняем в state
    if not args.dry_run:
        run_record = {
            "date": ts,
            "stats": {
                "updated": len(updated),
                "skipped_same": len(skipped_same),
                "skipped_zero": len(skipped_zero),
                "errors": len(errors),
                "total_products": len(product_by_id),
                "with_price": len(stock_price_by_id),
            },
            "changes": updated,  # полный список что изменилось
            "errors": errors
        }

        state["last_run"] = ts
        state["last_stats"] = run_record["stats"]
        state.setdefault("history", []).append(run_record)

        # Храним только последние N запусков
        if len(state["history"]) > HISTORY_KEEP:
            state["history"] = state["history"][-HISTORY_KEEP:]

        save_state(state)
        print(f"\nState сохранён: {STATE_FILE}")
    else:
        print(f"\n(dry-run — state не обновляется)")


if __name__ == "__main__":
    main()
