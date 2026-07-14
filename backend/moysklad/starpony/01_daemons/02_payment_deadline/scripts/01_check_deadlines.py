#!/usr/bin/env python3
"""
Мониторинг сроков оплаты по отгрузкам с отсрочкой платежа.

Читает все проведённые отгрузки, у которых:
  - есть контрагент со сроком отсрочки (поле "Срок отсрочки (дней)")
  - или на самой отгрузке стоит "Индивидуальный срок (дней)"
  - и сумма ещё не оплачена полностью

Выводит в консоль и пишет лог в data/deadlines.log.

Использование:
    python3 01_check_deadlines.py
    python3 01_check_deadlines.py --all   # показать все, включая оплаченные
"""

import sys
import os
import json
import argparse
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import MOYSKLAD_TOKEN, BASE_URL

HEADERS = {
    "Authorization": f"Bearer {MOYSKLAD_TOKEN}",
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip",
}

DATA_DIR = Path(__file__).parent.parent / "data"
LOG_FILE = DATA_DIR / "deadlines.log"

FIELD_COUNTERPARTY_DAYS = "Срок отсрочки (дней)"
FIELD_DEMAND_DAYS = "Индивидуальный срок (дней)"

WARN_DAYS = 3  # за сколько дней предупреждать


# === Helpers ===

def get_attribute_value(attributes: list, field_name: str):
    """Извлечь значение доп. поля по имени."""
    for attr in attributes or []:
        if attr.get("name") == field_name:
            return attr.get("value")
    return None


def parse_moment(moment_str: str) -> datetime:
    """Парсить дату МойСклад (2024-01-15 10:00:00.000)."""
    moment_str = moment_str.replace(" ", "T")
    if "." in moment_str:
        moment_str = moment_str[:moment_str.index(".")]
    return datetime.fromisoformat(moment_str)


def format_rub(kopecks: float) -> str:
    return f"{kopecks / 100:,.2f} ₽"


# === API ===

def get_all_pages(endpoint: str, params: dict = None) -> list:
    rows, offset = [], 0
    while True:
        p = (params or {}).copy()
        p["limit"] = 1000
        p["offset"] = offset
        resp = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=p, timeout=60)
        resp.raise_for_status()
        batch = resp.json().get("rows", [])
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def get_counterparty_days_map() -> dict:
    """
    Вернуть {counterparty_id: {"days": int, "name": str}} для всех контрагентов
    у которых заполнено поле 'Срок отсрочки (дней)'.
    """
    agents = get_all_pages("/entity/counterparty", {"expand": "attributes"})
    result = {}
    for agent in agents:
        days = get_attribute_value(agent.get("attributes", []), FIELD_COUNTERPARTY_DAYS)
        if days:
            result[agent["id"]] = {"days": int(days), "name": agent.get("name", "—")}
    return result


def get_demands_with_debt() -> list:
    """Получить проведённые отгрузки с expand на контрагента и доп. поля."""
    return get_all_pages("/entity/demand", {
        "filter": "applicable=true",
        "expand": "agent,attributes",
        "order": "moment,asc",
    })


def get_reports_with_debt() -> list:
    """Полученные отчёты комиссионера — именно по ним возникает долг комиссионера."""
    return get_all_pages("/entity/commissionreportin", {
        "filter": "applicable=true",
        "order": "moment,asc",
    })


def get_commission_contract_ids() -> set:
    """ID договоров комиссии. Отдельным запросом: expand у отгрузок
    не работает при limit>100, поэтому contractType оттуда не достать."""
    contracts = get_all_pages("/entity/contract", {})
    return {c["id"] for c in contracts if (c.get("contractType") or "").lower() == "commission"}


# === Основная логика ===

def analyze_documents(docs: list, counterparty_days: dict, show_all: bool, doc_kind: str = "demand",
                      commission_ids: set = frozenset()):
    """Единая логика дедлайнов для отгрузок (doc_kind="demand")
    и полученных отчётов комиссионера (doc_kind="report").

    Отгрузки по договору комиссии пропускаются: товар уходит на реализацию,
    долг возникает только по отчёту комиссионера, поэтому payedSum у таких
    отгрузок не заполняется никогда и контролировать их по оплате бессмысленно.

    Возвращает (results, skipped_commission).
    """
    is_demand = doc_kind == "demand"
    doc_label = "отгрузка" if is_demand else "отчёт комиссионера"
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    results = []
    skipped_commission = 0

    for d in docs:
        sum_kopecks = d.get("sum", 0) or 0
        payed_kopecks = d.get("payedSum", 0) or 0

        if is_demand:
            contract_href = ((d.get("contract") or {}).get("meta") or {}).get("href", "")
            if contract_href.rstrip("/").split("/")[-1] in commission_ids:
                skipped_commission += 1
                continue

        # Определяем срок отсрочки
        # Приоритет: индивидуальный срок на отгрузке > срок контрагента
        individual_days = get_attribute_value(d.get("attributes", []), FIELD_DEMAND_DAYS) if is_demand else None
        if individual_days:
            days = int(individual_days)
            days_source = "индивидуальный"
            agent = d.get("agent", {})
            agent_id = agent.get("id") or agent.get("meta", {}).get("href", "").split("/")[-1]
            agent_name = counterparty_days.get(agent_id, {}).get("name", "—")
        else:
            agent = d.get("agent", {})
            agent_id = agent.get("id") or agent.get("meta", {}).get("href", "").split("/")[-1]
            cp = counterparty_days.get(agent_id)
            if not cp:
                continue  # нет срока отсрочки — пропускаем
            days = cp["days"]
            agent_name = cp["name"]
            days_source = "контрагент"
        doc_name = d.get("name", "—")
        moment = parse_moment(d.get("moment", ""))
        deadline = moment + timedelta(days=days)
        days_left = (deadline.replace(hour=0, minute=0, second=0, microsecond=0) - today).days
        is_paid = payed_kopecks >= sum_kopecks and sum_kopecks > 0
        debt_kopecks = sum_kopecks - payed_kopecks

        if is_paid and not show_all:
            continue

        if is_paid:
            status = "✅ оплачено"
        elif days_left < 0:
            status = f"🔴 просрочено на {abs(days_left)} дн."
        elif days_left <= WARN_DAYS:
            status = f"🟡 осталось {days_left} дн."
        else:
            status = f"🟢 осталось {days_left} дн."

        results.append({
            "status": status,
            "is_paid": is_paid,
            "days_left": days_left,
            "doc_id": d.get("id"),
            "doc_name": doc_name,
            "agent_name": agent_name,
            "moment": moment.strftime("%d.%m.%Y"),
            "deadline": deadline.strftime("%d.%m.%Y"),
            "sum": sum_kopecks,
            "payed": payed_kopecks,
            "debt": debt_kopecks,
            "days": days,
            "days_source": days_source,
            "doc_type": doc_label,
            "ms_href": (d.get("meta") or {}).get("uuidHref", ""),
        })

    return results, skipped_commission


def print_results(results: list) -> str:
    lines = []

    overdue  = [r for r in results if not r["is_paid"] and r["days_left"] < 0]
    warning  = [r for r in results if not r["is_paid"] and 0 <= r["days_left"] <= WARN_DAYS]
    ok       = [r for r in results if not r["is_paid"] and r["days_left"] > WARN_DAYS]
    paid     = [r for r in results if r["is_paid"]]

    def section(title, items):
        if not items:
            return
        lines.append(f"\n{title} ({len(items)})")
        lines.append("─" * 70)
        for r in items:
            lines.append(
                f"  {r['status']:<30}  {r['agent_name'][:25]:<25}  {r['doc_name']}"
            )
            lines.append(
                f"    {r.get('doc_type', 'отгрузка').capitalize()}: {r['moment']}  →  Дедлайн: {r['deadline']}  "
                f"({r['days']} дн., {r['days_source']})"
            )
            if not r["is_paid"]:
                lines.append(
                    f"    Долг: {format_rub(r['debt'])}  "
                    f"(оплачено {format_rub(r['payed'])} из {format_rub(r['sum'])})"
                )

    section("🔴 ПРОСРОЧЕНО", overdue)
    section("🟡 СКОРО ИСТЕКАЕТ", warning)
    section("🟢 В НОРМЕ", ok)
    if paid:
        section("✅ ОПЛАЧЕНО", paid)

    if not results:
        lines.append("  Нет отгрузок с отсрочкой платежа.")

    lines.append(
        f"\nИтого: просрочено {len(overdue)}, "
        f"скоро {len(warning)}, "
        f"в норме {len(ok)}, "
        f"оплачено {len(paid)}"
    )
    return "\n".join(lines)


def export_results(results: list, path: str) -> None:
    """Структурированный JSON находок для страницы /checks (стандартный формат)."""
    import json
    from datetime import datetime as _dt

    overdue = [r for r in results if not r["is_paid"] and r["days_left"] < 0]
    warning = [r for r in results if not r["is_paid"] and 0 <= r["days_left"] <= WARN_DAYS]
    ok      = [r for r in results if not r["is_paid"] and r["days_left"] > WARN_DAYS]

    def _item(r, sev, lead):
        return {
            "key": "", "ms_id": r.get("doc_id") or "",
            "ms_href": r.get("ms_href") or "",
            "object": r["agent_name"], "severity": sev,
            "detail": f"{lead} · долг {format_rub(r['debt'])} · дедлайн {r['deadline']} · {r.get('doc_type', 'отгрузка')} №{r['doc_name']}",
        }

    categories = []
    if overdue:
        categories.append({"key": "overdue", "title": "Просрочено", "severity": "critical",
                           "kind": None, "ms_type": "demand", "count": len(overdue),
                           "items": [_item(r, "critical", f"просрочено на {abs(r['days_left'])} дн") for r in overdue]})
    if warning:
        categories.append({"key": "warning", "title": "Скоро истекает", "severity": "important",
                           "kind": None, "ms_type": "demand", "count": len(warning),
                           "items": [_item(r, "important", f"осталось {r['days_left']} дн") for r in warning]})
    if ok:
        categories.append({"key": "ok", "title": "В норме", "severity": "ok",
                           "kind": None, "ms_type": "demand", "count": len(ok),
                           "items": [_item(r, "ok", f"осталось {r['days_left']} дн") for r in ok]})

    payload = {
        "generated_at": _dt.now().isoformat(timespec="seconds"), "params": {},
        "summary": {"critical": len(overdue), "important": len(warning), "warnings": 0, "ok": len(ok)},
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Мониторинг сроков оплаты")
    parser.add_argument("--all", action="store_true", help="Показать в т.ч. оплаченные")
    parser.add_argument("--results-out", type=str, default=None,
                        help="Путь для структурированного JSON находок (для страницы /checks)")
    args = parser.parse_args()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"\n{'=' * 70}\nМОНИТОРИНГ ОТСРОЧЕК ПЛАТЕЖА — {now_str}\n{'=' * 70}"
    print(header)

    print("Загружаем контрагентов...")
    counterparty_map = get_counterparty_days_map()
    print(f"  Контрагентов со сроком отсрочки: {len(counterparty_map)}")

    if not counterparty_map:
        print("\nНет контрагентов с заполненным полем «Срок отсрочки (дней)».")
        print("Заполните поле хотя бы у одного контрагента в МойСклад.")
        if args.results_out:
            try:
                export_results([], args.results_out)
            except Exception as e:
                print(f"Ошибка сохранения результатов JSON: {e}")
        return

    print("Загружаем отгрузки...")
    demands = get_demands_with_debt()
    print(f"  Проведённых отгрузок: {len(demands)}")

    print("Загружаем отчёты комиссионера...")
    reports = get_reports_with_debt()
    print(f"  Отчётов комиссионера: {len(reports)}")

    commission_ids = get_commission_contract_ids()
    print(f"  Договоров комиссии: {len(commission_ids)}")

    demand_results, skipped = analyze_documents(demands, counterparty_map, show_all=args.all,
                                                doc_kind="demand", commission_ids=commission_ids)
    report_results, _ = analyze_documents(reports, counterparty_map, show_all=args.all, doc_kind="report")
    if skipped:
        print(f"  Пропущено комиссионных отгрузок: {skipped} (долг комиссионера контролируется по отчётам)")

    results = demand_results + report_results
    results.sort(key=lambda x: (x["is_paid"], x["days_left"]))
    output = print_results(results)
    print(output)

    if args.results_out:
        try:
            export_results(results, args.results_out)
        except Exception as e:
            print(f"Ошибка сохранения результатов JSON: {e}")

    # Пишем лог
    DATA_DIR.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(header + "\n")
        f.write(output + "\n")
    print(f"\nЛог записан: {LOG_FILE}")


if __name__ == "__main__":
    main()
