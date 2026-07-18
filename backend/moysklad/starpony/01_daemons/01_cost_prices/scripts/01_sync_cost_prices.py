#!/usr/bin/env python3
"""
Синхронизация себестоимости из FIFO МойСклад → тип цены "Себестоимость".

Запускается по cron. Читает FIFO-себестоимость из /report/stock/all
и обновляет тип цены "Себестоимость" у товаров из папки "Готовая продукция".
Дату последнего обновления пишет в доп. поле товара.

История запусков хранится в data/.sync_state.json.

Использование:
    python3 01_sync_cost_prices.py             # реальное обновление
    python3 01_sync_cost_prices.py --dry-run   # только показать что изменится
"""

import sys
import os
import time
import json
import argparse
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import MOYSKLAD_TOKEN, BASE_URL

HEADERS = {
    "Authorization": f"Bearer {MOYSKLAD_TOKEN}",
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip",
}

DATA_DIR = Path(__file__).parent.parent / "data"
STATE_FILE = DATA_DIR / ".sync_state.json"
DELAY = 0.2

COST_PRICE_TYPE_NAME = "Себестоимость"
DATE_FIELD_NAME = "Дата обновления себестоимости"


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

def get_all_pages(endpoint: str, params: dict = None) -> list:
    all_rows, offset = [], 0
    while True:
        p = (params or {}).copy()
        p["limit"] = 1000
        p["offset"] = offset
        resp = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=p, timeout=60)
        resp.raise_for_status()
        rows = resp.json().get("rows", [])
        all_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000
        time.sleep(DELAY)
    return all_rows


def get_cost_price_type() -> dict:
    """Найти тип цены 'Себестоимость' и вернуть его мету."""
    types = requests.get(
        f"{BASE_URL}/context/companysettings/pricetype",
        headers=HEADERS, timeout=30
    ).json()
    for t in types:
        if t["name"] == COST_PRICE_TYPE_NAME:
            return t
    raise RuntimeError(f"Тип цены '{COST_PRICE_TYPE_NAME}' не найден")


def get_rub_currency_meta() -> dict:
    resp = requests.get(f"{BASE_URL}/entity/currency", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    for c in resp.json().get("rows", []):
        if c.get("default"):
            return c["meta"]
    raise RuntimeError("Дефолтная валюта не найдена")


def get_date_field_meta() -> dict | None:
    resp = requests.get(
        f"{BASE_URL}/entity/product/metadata/attributes",
        headers=HEADERS, timeout=30
    )
    resp.raise_for_status()
    for attr in resp.json().get("rows", []):
        if attr["name"] == DATE_FIELD_NAME:
            return attr["meta"]
    return None


def get_all_products() -> dict:
    """Вернуть словарь {product_id: product} для всех товаров."""
    all_products = []
    offset = 0
    while True:
        url = f"{BASE_URL}/entity/product?limit=1000&offset={offset}"
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        rows = resp.json().get("rows", [])
        all_products.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000
    return {p["id"]: p for p in all_products}


def get_fifo_by_product() -> dict:
    """Вернуть словарь {product_id: fifo_kopecks} из /report/stock/all."""
    items = get_all_pages("/report/stock/all")
    result = {}
    for item in items:
        if item.get("meta", {}).get("type") != "product":
            continue
        pid = item["meta"]["href"].split("/")[-1].split("?")[0]
        price = round(item.get("price", 0) or 0)
        if price > 0:
            result[pid] = price
    return result


def update_product_cost_price(
    product_id: str,
    fifo_kopecks: int,
    existing_sale_prices: list,
    cost_type_meta: dict,
    currency_meta: dict,
    date_field_meta: dict | None,
    now_str: str,
):
    """Обновить тип цены 'Себестоимость' не затрагивая остальные цены."""
    # Берём существующие цены продажи, заменяем/добавляем Себестоимость
    new_prices = [p for p in existing_sale_prices
                  if p.get("priceType", {}).get("meta", {}).get("href") != cost_type_meta["href"]]
    new_prices.append({
        "value": fifo_kopecks,
        "currency": {"meta": currency_meta},
        "priceType": {"meta": cost_type_meta},
    })

    payload = {"salePrices": new_prices}
    if date_field_meta:
        payload["attributes"] = [{"meta": date_field_meta, "value": now_str}]

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
        {"label": "Нет остатков", "value": len(skipped_zero), "tone": "neutral",
         **({"cat": "skipped_zero"} if skipped_zero else {})},
        {"label": "Ошибки", "value": len(errors), "tone": "critical" if errors else "neutral"},
    ]
    categories = []
    if skipped_zero:
        categories.append({
            "key": "skipped_zero", "title": "Товары без остатков", "severity": "info",
            "kind": None, "ms_type": None, "count": len(skipped_zero),
            "items": [{"key": "", "ms_id": "", "object": name, "severity": "info",
                       "detail": "нет остатков на складе (или FIFO = 0) — себестоимость не пересчитывается"}
                      for name in skipped_zero],
        })
    if updated:
        items = []
        for c in updated:
            d = c.get("new_rub", 0) - c.get("old_rub", 0)
            sign = "+" if d > 0 else ""
            items.append({"key": "", "ms_id": "", "object": c["name"], "severity": "info",
                          "detail": f"{c.get('old_rub', 0):.2f} → {c.get('new_rub', 0):.2f} ₽ ({sign}{d:.2f})"})
        categories.append({"key": "updated", "title": "Обновлённая себестоимость", "severity": "info",
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
    parser = argparse.ArgumentParser(description="Синхронизация себестоимости из FIFO")
    parser.add_argument("--dry-run", action="store_true", help="Только показать изменения")
    parser.add_argument("--results-out", type=str, default=None,
                        help="Путь для структурированного JSON находок (для страницы /checks)")
    args = parser.parse_args()

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S.000")
    ts = now.strftime("%Y-%m-%d %H:%M")

    print("=== Синхронизация себестоимости — StarPony ===")
    print(f"Дата: {ts}")
    if args.dry_run:
        print("⚠️  DRY RUN — изменений не будет")
    print()

    state = load_state()
    if state.get("last_run"):
        last = state.get("last_stats", {})
        print(f"Последний запуск: {state['last_run']} "
              f"(обновлено: {last.get('updated', 0)}, ошибок: {last.get('errors', 0)})")
        print()

    print("1. Получаем тип цены 'Себестоимость'...")
    cost_type = get_cost_price_type()
    cost_type_meta = cost_type["meta"]
    print(f"   ОК: id={cost_type['id']}")

    print("2. Получаем валюту (RUB)...")
    currency_meta = get_rub_currency_meta()
    print("   ОК")

    print(f"3. Ищем доп. поле '{DATE_FIELD_NAME}'...")
    date_field_meta = get_date_field_meta()
    print(f"   {'Найдено ✅' if date_field_meta else 'Не найдено — дата записываться не будет'}")

    print(f"\n4. Загружаем все товары...")
    all_products = get_all_products()
    print(f"   Товаров: {len(all_products)}")

    print("\n5. Загружаем FIFO-себестоимость из /report/stock/all...")
    fifo = get_fifo_by_product()
    # Оставляем только те товары которые есть в системе
    fifo = {pid: v for pid, v in fifo.items() if pid in all_products}
    print(f"   Товаров с ненулевой FIFO: {len(fifo)}")

    print("\n6. Сравниваем и обновляем...\n")

    updated, skipped_same, skipped_zero, errors = [], [], [], []

    for pid, fifo_kopecks in sorted(fifo.items(),
                                    key=lambda x: all_products[x[0]].get("name", "")):
        product = all_products[pid]
        name = product.get("name", "—")
        fifo_rub = fifo_kopecks / 100

        # Текущая себестоимость из salePrices
        current_kopecks = 0
        for sp in product.get("salePrices", []):
            if sp.get("priceType", {}).get("meta", {}).get("href") == cost_type_meta["href"]:
                current_kopecks = sp.get("value", 0) or 0
                break
        current_rub = current_kopecks / 100

        if fifo_kopecks == current_kopecks:
            skipped_same.append(name)
            continue

        delta = fifo_rub - current_rub
        sign = "+" if delta > 0 else ""
        print(f"  {name[:60]:<60}  {current_rub:.2f} → {fifo_rub:.2f} руб  ({sign}{delta:.2f})")

        change = {"name": name, "id": pid, "old_rub": current_rub, "new_rub": fifo_rub}

        if args.dry_run:
            updated.append(change)
        else:
            try:
                time.sleep(DELAY)
                update_product_cost_price(
                    pid, fifo_kopecks,
                    product.get("salePrices", []),
                    cost_type_meta, currency_meta,
                    date_field_meta, now_str
                )
                print(f"    ✅ обновлено")
                updated.append(change)
            except Exception as e:
                print(f"    ❌ {e}")
                errors.append({"name": name, "id": pid, "error": str(e)})

    # Товары без FIFO (нет остатков)
    for pid, product in all_products.items():
        if pid not in fifo:
            skipped_zero.append(product.get("name", "—"))

    print(f"\n{'=' * 60}")
    action = "Будет обновлено" if args.dry_run else "Обновлено"
    print(f"ИТОГ:")
    print(f"  {action}:                  {len(updated)}")
    print(f"  Уже актуальные:            {len(skipped_same)}")
    print(f"  Нет остатков/FIFO=0:       {len(skipped_zero)}")
    if errors:
        print(f"  Ошибки:                    {len(errors)}")
    print(f"{'=' * 60}")

    if args.results_out:
        try:
            _export_results(updated, skipped_same, skipped_zero, errors, args.results_out)
        except Exception as e:
            print(f"Ошибка сохранения результатов JSON: {e}")

    if not args.dry_run:
        run_record = {
            "date": ts,
            "stats": {
                "updated": len(updated),
                "skipped_same": len(skipped_same),
                "skipped_zero": len(skipped_zero),
                "errors": len(errors),
            },
            "changes": updated,
            "errors": errors,
        }
        state["last_run"] = ts
        state["last_stats"] = run_record["stats"]
        state.setdefault("history", []).append(run_record)
        if len(state["history"]) > 90:
            state["history"] = state["history"][-90:]
        save_state(state)
        print(f"\nState сохранён: {STATE_FILE}")


if __name__ == "__main__":
    main()
