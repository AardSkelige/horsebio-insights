#!/usr/bin/env python3
"""Сверка заказов сайта horse-bio.ru с тем, что робот завёл в МойСклад.

Робот заводит заказы из писем, а письмо не передаёт скидку: позиции в нём идут
по РРЦ, а итог уже со скидкой. Раскладку робот считает сам (split_site_discount
в order_email_utils), и эта проверка — независимый контроль: выгрузка сайта
отдаёт цены нетто и сами скидки, посчитанные самим сайтом.

Что ловим:
  • заказ оплачен на сайте, а в МойСклад его нет — робот пропустил;
  • сумма заказа в МойСклад разошлась с итогом сайта — скидка не учтена;
  • оплата не сходится с суммой заказа — тот самый «частично оплачено», из-за
    которого отгрузка вешает на покупателя несуществующий долг.

Чего проверка не умеет: если заказ пересоздали в МойСклад руками, у документа
не будет ни externalCode с номером заказа сайта, ни канала продаж — сверка будет
считать его отсутствующим. Пока таких случаев не было; если начнут накапливаться,
нужен список подтверждённых исключений, как в health-чеке.

Порядок работы с сайтом важен и необратим: `mode=query` отдаёт 500 самых старых
неподтверждённых заказов, а сдвинуть окно к свежим можно только через
`mode=success`, после которого заказ исчезает из выгрузки навсегда. Поэтому
сначала пишем прочитанное на диск и только потом подтверждаем; если запись
не удалась — не подтверждаем вовсе, лучше перечитать то же окно ещё раз.

Логика сверки живёт в reconcile_core.py — она под тестами.

Запуск:
  python3 01_reconcile_site_orders.py
  python3 01_reconcile_site_orders.py --no-acknowledge   # не сдвигать окно выгрузки
  python3 01_reconcile_site_orders.py --results-out out.json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import ProductionHelper, MOYSKLAD_TOKEN, BASE_URL  # noqa: E402
from site_orders_export import SiteOrdersExport, SiteExportError  # noqa: E402
from reconcile_core import (  # noqa: E402
    ROBOT_START, WINDOW_SIZE, build_payload, compare, fetch_age_days, load_store, sync_window,
)

STORE_FILE = Path(__file__).parent.parent / "data" / "site_orders.json"

# Канал продаж «Прочее | Сайт Horse-Bio» — тот же, что проставляет робот
SALES_CHANNEL_ID = "af781aeb-711c-11f0-0a80-1a56002f3340"


def ms_orders_by_external_code(helper: ProductionHelper) -> dict:
    channel = f"{BASE_URL}/entity/saleschannel/{SALES_CHANNEL_ID}"
    # Ограничиваем период: до старта робота сверять нечего (см. ROBOT_START),
    # а без фильтра выборка растёт вместе с историей канала
    rows = helper._get_all_pages("/entity/customerorder", {
        "filter": f"salesChannel={channel};moment>={ROBOT_START} 00:00:00"})
    return {row["externalCode"]: row for row in rows if row.get("externalCode")}


def main():
    parser = argparse.ArgumentParser(description="Сверка заказов сайта с МойСклад")
    parser.add_argument("--no-acknowledge", action="store_true",
                        help="не подтверждать окно выгрузки (свежие заказы не появятся)")
    parser.add_argument("--results-out", type=str, default=None,
                        help="путь для структурированного JSON находок (страница /checks)")
    args = parser.parse_args()

    print(f"{'=' * 64}\nСверка заказов сайта: {datetime.now():%Y-%m-%d %H:%M:%S}\n{'=' * 64}")

    export_error, stale_days = None, None
    try:
        result = sync_window(SiteOrdersExport(), STORE_FILE,
                             acknowledge=not args.no_acknowledge)
        stale_days = result["stale_days"]
        if result["refused"]:
            print("  Сайт заказов не отдал (обмен ответил отказом вместо документа)"
                  + (f" — последняя удачная выгрузка {stale_days} дн. назад" if stale_days else ""))
        else:
            print(f"  Прочитано из выгрузки: {result['window']} (новых {result['fresh']})")
        if result["lost"]:
            print(f"  WARNING: {len(result['lost'])} заказов не сохранились на диск — "
                  f"окно НЕ подтверждаю")
        elif result["ack"] is not None:
            print(f"  Окно подтверждено, ответ сайта: {result['ack'][:80]}")
        elif args.no_acknowledge:
            print("  Окно НЕ подтверждено (--no-acknowledge)")
        elif not result["refused"] and result["window"] < WINDOW_SIZE:
            print(f"  Окно неполное ({result['window']} < {WINDOW_SIZE}) — не подтверждаю: "
                  f"перечитывая его, видим свежий статус оплаты")
        if result["dropped"]:
            print(f"  Выкинуто из хранилища как слишком старое: {result['dropped']}")
        stale_days = result["stale_days"]
    except SiteExportError as e:
        # Сайт мог прилечь — сверяем по сохранённой копии, а не падаем целиком.
        # Сам факт обязательно уходит в находки, иначе /checks покажет зелёное.
        export_error = str(e)
        stale_days = fetch_age_days(load_store(STORE_FILE))
        print(f"  WARNING: выгрузка недоступна ({e}) — сверяю по сохранённой копии")

    store = load_store(STORE_FILE)
    helper = ProductionHelper(MOYSKLAD_TOKEN)
    findings, checked = compare(store, ms_orders_by_external_code(helper))

    print(f"\n  Сверено оплаченных заказов с {ROBOT_START}: {checked}")
    for key, title in (("missing", "Нет в МойСклад"),
                       ("sum_mismatch", "Сумма разошлась"),
                       ("unpaid", "Оплата не сходится")):
        rows = findings[key]
        if not rows:
            continue
        print(f"\n  {title}: {len(rows)}")
        for order, ms in rows:
            ms_sum = (ms.get("sum") or 0) / 100 if ms else 0
            ms_paid = (ms.get("payedSum") or 0) / 100 if ms else 0
            print(f"    №{order.number:<6} {order.date}  сайт {order.total:>9.2f} ₽  "
                  f"МС {ms_sum:>9.2f} ₽  оплачено {ms_paid:>9.2f} ₽"
                  + (f"  [{ms['name']}]" if ms else "  [не заведён]"))
    if not any(findings.values()):
        print("  Расхождений нет")
    print('=' * 64)

    if args.results_out:
        try:
            Path(args.results_out).write_text(
                json.dumps(build_payload(findings, checked, export_error, stale_days),
                           ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError as e:
            print(f"Ошибка сохранения результатов JSON: {e}")


if __name__ == "__main__":
    main()
