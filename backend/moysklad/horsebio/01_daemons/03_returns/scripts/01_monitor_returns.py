#!/usr/bin/env python3
"""
Монитор возвратов покупателей для ВБ и Озон.

Следит за заказами покупателей со статусами "Возврат" и "Отменен",
создаёт документы возвратов покупателей (salesreturn) если их нет.

Яндекс Маркет синхронизация создаёт возвраты сама — не трогаем.
История до 2026-03-04 не трогается.

Запуск:
  cd 01_daemons/03_returns/scripts && python3 01_monitor_returns.py
  python3 01_monitor_returns.py              # однократная проверка
  python3 01_monitor_returns.py --daemon     # режим демона (каждые 5 минут)
  python3 01_monitor_returns.py --dry-run    # пробный прогон без создания документов
  python3 01_monitor_returns.py --force      # перепроверить всё с START_DATE
"""

import json
import time
import argparse
import sys
import os
import requests as _requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import ProductionHelper, MOYSKLAD_TOKEN, BASE_URL

# Файл состояния
STATE_FILE = Path(__file__).parent.parent / "data" / ".returns_state.json"

# Стартовая дата — историю до этой даты не трогаем
START_DATE = "2026-03-04 00:00:00"

# Статусы заказов для обработки
STATES = {
    "Возврат": f"{BASE_URL}/entity/customerorder/metadata/states/41e67a4d-266b-11eb-0a80-090200155ca0",
    "Отменен": f"{BASE_URL}/entity/customerorder/metadata/states/41e67be8-266b-11eb-0a80-090200155ca1",
}

# Агенты для обработки — только ВБ и Озон
TARGET_AGENTS = ["Вайлдберриз (Вб)", "Вб Вайлдберриз", "Озон"]


class ReturnsMonitor:
    """Монитор возвратов покупателей для маркетплейсов ВБ и Озон"""

    def __init__(self, helper: ProductionHelper, dry_run: bool = False):
        self.helper = helper
        self.dry_run = dry_run
        self.state = self._load_state()

    def _load_state(self) -> dict:
        """Загрузить состояние из файла"""
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
        return {
            "last_run": START_DATE,
            "processed_orders": {}
        }

    def _save_state(self):
        """Сохранить состояние в файл"""
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False, default=str)
        )

    def _get_orders_with_status(self, status_name: str, state_href: str) -> list:
        """
        Получить заказы с нужным статусом, обновлённые после last_run.
        МойСклад требует два отдельных параметра filter (не через ;).
        """
        last_run = self.state.get("last_run", START_DATE)
        all_orders = []
        offset = 0

        while True:
            # Два filter параметра передаём как список кортежей (requests поддерживает)
            params = [
                ("filter", f"state={state_href}"),
                ("filter", f"updated>={last_run}"),
                ("expand", "agent,state,demands"),
                ("order", "updated,asc"),
                ("limit", "100"),
                ("offset", str(offset)),
            ]
            response = _requests.get(
                f"{BASE_URL}/entity/customerorder",
                headers=self.helper.headers,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            result = response.json()
            rows = result.get("rows", [])
            all_orders.extend(rows)

            if len(rows) < 100:
                break
            offset += 100

        return all_orders

    def _get_demand_details(self, demand_id: str) -> dict:
        """Получить полные данные отгрузки с позициями и проверкой возвратов"""
        return self.helper._get(
            f"/entity/demand/{demand_id}",
            {"expand": "positions.assortment,organization,agent,store,contract,salesChannel"}
        )

    def _demand_has_return(self, demand: dict) -> bool:
        """
        Проверить есть ли уже возврат у отгрузки.
        returns может быть:
          - list: [...] — прямой список ссылок
          - dict: {"meta": {"size": N, ...}} — коллекция с размером
          - None/отсутствует — нет возвратов
        """
        returns = demand.get("returns")
        if not returns:
            return False
        if isinstance(returns, list):
            return len(returns) > 0
        if isinstance(returns, dict):
            # Попытка 1: поле rows (если expand=returns)
            rows = returns.get("rows")
            if rows is not None:
                return len(rows) > 0
            # Попытка 2: meta.size (коллекция без expand)
            size = returns.get("meta", {}).get("size", 0)
            return size > 0
        return False

    def _extract_meta(self, field: dict) -> dict:
        """Извлечь {meta: ...} из поля сущности"""
        if isinstance(field, dict) and "meta" in field:
            return {"meta": field["meta"]}
        return field

    def _evaluate_return_cost(self, store_meta: dict, moment: str, positions_raw: list) -> dict:
        """
        Вызвать wizard/salesreturn?action=evaluate_cost для получения себестоимости позиций.
        Возвращает dict: {assortment_href → cost_kopecks}.
        При ошибке возвращает пустой dict (позиции создадутся без cost — не хуже прежнего).
        """
        wizard_positions = []
        for pos in positions_raw:
            assortment_meta = pos.get("assortment", {}).get("meta")
            if not assortment_meta:
                continue
            wizard_positions.append({
                "quantity": pos.get("quantity", 0),
                "assortment": {"meta": assortment_meta},
            })

        if not wizard_positions:
            return {}

        payload = {
            "store":     {"meta": store_meta.get("meta", store_meta)},
            "moment":    moment,
            "positions": wizard_positions,
        }

        try:
            resp = _requests.post(
                f"{BASE_URL}/wizard/salesreturn",
                headers=self.helper.headers,
                params={"action": "evaluate_cost"},
                json=payload,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"    WARNING: wizard evaluate_cost вернул {resp.status_code} — создаём без себестоимости")
                return {}
            data = resp.json()
            cost_map = {}
            for p in data.get("positions", []):
                href = p.get("assortment", {}).get("meta", {}).get("href", "")
                cost_map[href] = p.get("cost", 0)
            return cost_map
        except Exception as e:
            print(f"    WARNING: wizard evaluate_cost — ошибка {e} — создаём без себестоимости")
            return {}

    def _create_sales_return(self, order: dict, demand: dict) -> dict | None:
        """Создать черновик возврата покупателя на основе отгрузки"""
        order_name = order.get("name", "?")
        status_name = order.get("state", {}).get("name", "?")
        demand_name = demand.get("name", "?")

        # Позиции из отгрузки
        positions_data = demand.get("positions", {})
        if isinstance(positions_data, dict):
            positions_rows = positions_data.get("rows", [])
        elif isinstance(positions_data, list):
            positions_rows = positions_data
        else:
            positions_rows = []

        if not positions_rows:
            print(f"    WARNING: У отгрузки {demand_name} нет позиций — пропускаем")
            return None

        # Получаем себестоимость через wizard-эндпоинт.
        # Поле называется "cost" (не "costPrice") — специфика API salesreturn.
        # wizard вычисляет себестоимость на момент возврата по методу FIFO.
        store_raw = demand.get("store", {})
        moment = order.get("moment", demand.get("moment", ""))

        wizard_cost_map = self._evaluate_return_cost(
            store_raw,
            moment,
            positions_rows,
        )
        if wizard_cost_map:
            print(f"    INFO: wizard вернул себестоимость для {len(wizard_cost_map)} позиций")
        else:
            print(f"    WARNING: себестоимость не получена — создаём без поля cost")

        return_positions = []
        for pos in positions_rows:
            assortment_meta = pos.get("assortment", {}).get("meta")
            if not assortment_meta:
                continue
            assortment_href = assortment_meta.get("href", "")
            entry = {
                "quantity": pos.get("quantity", 0),
                "price":    pos.get("price", 0),
                "discount": pos.get("discount", 0),
                "vat":      pos.get("vat", 0),
                "assortment": {"meta": assortment_meta},
            }
            # Добавляем "cost" только если wizard вернул значение > 0
            cost_val = wizard_cost_map.get(assortment_href, 0)
            if cost_val > 0:
                entry["cost"] = cost_val
            return_positions.append(entry)

        if not return_positions:
            print(f"    WARNING: Не удалось сформировать позиции для {order_name}")
            return None

        payload = {
            "applicable": False,
            "description": f"Авто: возврат по заказу {order_name} (статус: {status_name})",
            "organization": self._extract_meta(demand.get("organization", {})),
            "agent": self._extract_meta(demand.get("agent", {})),
            "store": self._extract_meta(demand.get("store", {})),
            "demand": {"meta": demand.get("meta", {})},
            "positions": return_positions,
        }

        # Договор и канал продаж — берём из отгрузки если есть
        if demand.get("contract") and demand["contract"].get("meta"):
            payload["contract"] = self._extract_meta(demand["contract"])
        if demand.get("salesChannel") and demand["salesChannel"].get("meta"):
            payload["salesChannel"] = self._extract_meta(demand["salesChannel"])

        if self.dry_run:
            print(f"    [DRY-RUN] POST /entity/salesreturn: "
                  f"заказ {order_name} → отгрузка {demand_name}, "
                  f"{len(return_positions)} позиций")
            return {"id": "dry-run", "name": "dry-run"}

        return self.helper._post("/entity/salesreturn", payload)

    def _process_order(self, order: dict) -> str:
        """
        Обработать один заказ покупателя.
        Returns: 'skipped' | 'already_processed' | 'no_demand' |
                 'return_exists' | 'return_created' | 'error'
        """
        order_id = order.get("id")
        order_name = order.get("name", "?")
        agent_name = order.get("agent", {}).get("name", "?")
        status_name = order.get("state", {}).get("name", "?")

        # Обрабатываем только ВБ и Озон
        if agent_name not in TARGET_AGENTS:
            return "skipped"

        # Уже обработан ранее?
        if order_id in self.state["processed_orders"]:
            return "already_processed"

        # Получаем отгрузки (demands — это list при expand=demands)
        demands = order.get("demands") or []

        if not demands:
            shipped_sum = order.get("shippedSum", 0) / 100

            # Отменён и не отгружался — товар не двигался, возвращать нечего. Это не
            # пробел, а штатная отмена до отгрузки: не считаем проблемой и не показываем.
            # (Отгружённый и затем отменённый заказ имеет demands и идёт по ветке ниже.)
            if status_name == "Отменен":
                print(f"  SKIP: {order_name} ({agent_name}) — отменён без отгрузки, возврат не нужен")
                self.state["processed_orders"][order_id] = {
                    "order_name": order_name,
                    "agent": agent_name,
                    "status_name": status_name,
                    "status": "cancelled_no_ship",
                    "shipped_sum": shipped_sum,
                    "processed_at": datetime.now().isoformat()
                }
                return "cancelled_no_ship"

            # Извлекаем тип доставки из комментария синхронизации
            description = order.get("description", "")
            delivery_type = ""
            for line in description.splitlines():
                if "Тип доставки:" in line:
                    delivery_type = line.split("Тип доставки:")[-1].strip()
                    break
                if "Тип интеграции со службой доставки:" in line:
                    delivery_type = line.split("Тип интеграции со службой доставки:")[-1].strip()
                    break
            fbo_hint = " — предположительно ФБО" if shipped_sum == 0 and delivery_type else ""
            delivery_info = f", тип доставки: {delivery_type}" if delivery_type else ""
            print(f"  SKIP: {order_name} ({agent_name}, {status_name}) — нет документа отгрузки{fbo_hint}{delivery_info}")
            self.state["processed_orders"][order_id] = {
                "order_name": order_name,
                "agent": agent_name,
                "status_name": status_name,
                "status": "no_demand",
                "shipped_sum": shipped_sum,
                "processed_at": datetime.now().isoformat()
            }
            return "no_demand"

        # Быстрая проверка: возврат уже есть у любой из отгрузок (данные из expand)
        if any(self._demand_has_return(dm) for dm in demands):
            print(f"  OK: {order_name} ({agent_name}) — возврат уже есть")
            self.state["processed_orders"][order_id] = {
                "order_name": order_name,
                "agent": agent_name,
                "status_name": status_name,
                "status": "return_exists",
                "processed_at": datetime.now().isoformat()
            }
            return "return_exists"

        # Выбираем отгрузку с позициями: у заказа их может быть несколько,
        # в т.ч. пустых (0 позиций) — из пустой возврат не создать
        demand_detail = None
        for dm in demands:
            demand_id = dm.get("id") or dm.get("meta", {}).get("href", "").split("/")[-1].split("?")[0]
            if not demand_id:
                continue
            try:
                detail = self._get_demand_details(demand_id)
            except Exception as e:
                print(f"  ERROR: {order_name} — ошибка получения отгрузки {demand_id}: {e}")
                return "error"

            # Повторная проверка возвратов (на случай если в expand не было данных)
            if self._demand_has_return(detail):
                print(f"  OK: {order_name} ({agent_name}) — возврат уже есть (подтверждено)")
                self.state["processed_orders"][order_id] = {
                    "order_name": order_name,
                    "agent": agent_name,
                    "status_name": status_name,
                    "status": "return_exists",
                    "processed_at": datetime.now().isoformat()
                }
                return "return_exists"

            positions = detail.get("positions", {})
            rows = positions.get("rows", []) if isinstance(positions, dict) else positions
            if rows:
                demand_detail = detail
                break
            print(f"    WARNING: отгрузка {detail.get('name', '?')} без позиций — пробуем следующую")

        if demand_detail is None:
            print(f"  ERROR: {order_name} — ни в одной из {len(demands)} отгрузок нет позиций")
            return "error"

        # Создаём возврат
        print(f"  CREATE: {order_name} ({agent_name}, {status_name}) → отгрузка {demand_detail.get('name', '?')}")

        try:
            result = self._create_sales_return(order, demand_detail)
            if result is None:
                return "error"

            return_name = result.get("name", "?")
            return_id = result.get("id")
            print(f"  ✅ Создан черновик возврата {return_name} для заказа {order_name}")

            self.state["processed_orders"][order_id] = {
                "order_name": order_name,
                "agent": agent_name,
                "status_name": status_name,
                "status": "return_created",
                "return_id": return_id,
                "return_name": return_name,
                "processed_at": datetime.now().isoformat()
            }
            return "return_created"

        except Exception as e:
            print(f"  ERROR: {order_name} — ошибка создания возврата: {e}")
            return "error"

    def run_once(self):
        """Одна итерация мониторинга"""
        print(f"\n{'='*60}")
        print(f"Проверка возвратов: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.dry_run:
            print("[DRY-RUN — документы НЕ создаются]")
        print(f"{'='*60}")

        last_run = self.state.get("last_run", START_DATE)
        print(f"Заказы обновлённые после: {last_run}")
        print(f"Агенты: {', '.join(TARGET_AGENTS)}")

        run_start = datetime.now()

        counts = {
            "skipped": 0,
            "already_processed": 0,
            "no_demand": 0,
            "cancelled_no_ship": 0,
            "return_exists": 0,
            "return_created": 0,
            "error": 0,
        }
        details = {}

        for status_name, state_href in STATES.items():
            print(f"\n--- Статус: {status_name} ---")
            orders = self._get_orders_with_status(status_name, state_href)

            target_count = sum(
                1 for o in orders
                if o.get("agent", {}).get("name") in TARGET_AGENTS
            )
            print(f"Найдено: {len(orders)} заказов (ВБ+Озон: {target_count})")

            for order in orders:
                result = self._process_order(order)
                counts[result] = counts.get(result, 0) + 1
                details.setdefault(result, []).append({
                    "order_name": order.get("name", "?"),
                    "agent": order.get("agent", {}).get("name", ""),
                    "status_name": status_name,
                    "order_date": (order.get("moment") or "")[:10],
                })

        # Обновляем last_run после успешного прогона
        if not self.dry_run:
            self.state["last_run"] = run_start.strftime("%Y-%m-%d %H:%M:%S")
            self._save_state()

        # Итоги
        print(f"\n{'='*60}")
        print("Итого:")
        print(f"  Не наши агенты (ЯМ и др.):  {counts['skipped']}")
        print(f"  Уже обработаны ранее:        {counts['already_processed']}")
        print(f"  Отменён без отгрузки:        {counts['cancelled_no_ship']}")
        print(f"  Нет отгрузки (WARNING):      {counts['no_demand']}")
        print(f"  Возврат уже существует:      {counts['return_exists']}")
        print(f"  Создано новых возвратов:     {counts['return_created']}")
        print(f"  Ошибки:                      {counts['error']}")
        print(f"{'='*60}")

        return counts, details


def _export_results(counts, details, path):
    """Структурированный JSON для страницы /checks: стат-карточки + раскрываемые списки."""
    import json as _json
    from datetime import datetime as _dt

    cr, re_, nd, er, sk = (counts.get(k, 0) for k in ("return_created", "return_exists", "no_demand", "error", "skipped"))
    stats = [
        {"label": "Создано возвратов", "value": cr, "tone": "ok" if cr else "neutral", **({"cat": "created"} if cr else {})},
        {"label": "Уже существуют", "value": re_, "tone": "neutral"},
        {"label": "Нет отгрузки", "value": nd, "tone": "warning" if nd else "neutral", **({"cat": "no_demand"} if nd else {})},
        {"label": "Ошибки", "value": er, "tone": "critical" if er else "neutral", **({"cat": "errors"} if er else {})},
        {"label": "Не ВБ/Озон", "value": sk, "tone": "neutral"},
    ]

    def cat(key, title, sev, src):
        items = [{"key": "", "ms_id": "", "object": f"Заказ №{d['order_name']}", "severity": sev,
                  "detail": f"{d.get('agent', '')} · статус: {d.get('status_name', '')}"
                            + (f" · заказ от {d['order_date']}" if d.get('order_date') else '')}
                 for d in (details.get(src) or [])]
        return {"key": key, "title": title, "severity": sev, "kind": None, "ms_type": None,
                "count": len(items), "items": items} if items else None

    categories = [c for c in [
        cat("errors", "Ошибки создания", "critical", "error"),
        cat("no_demand", "Нет отгрузки (возврат не создан)", "important", "no_demand"),
        cat("created", "Созданные возвраты", "ok", "return_created"),
    ] if c]

    payload = {
        "generated_at": _dt.now().isoformat(timespec="seconds"), "params": {},
        "summary": {"critical": counts.get("error", 0), "important": counts.get("no_demand", 0),
                    "warnings": 0, "ok": counts.get("return_created", 0), "stats": stats},
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Монитор возвратов покупателей для ВБ и Озон"
    )
    parser.add_argument("--daemon", action="store_true",
                        help="Запустить как демон")
    parser.add_argument("--interval", type=int, default=300,
                        help="Интервал проверки в секундах (по умолчанию 300)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Пробный прогон без создания документов")
    parser.add_argument("--force", action="store_true",
                        help=f"Сбросить state и проверить всё с {START_DATE}")
    parser.add_argument("--results-out", type=str, default=None,
                        help="Путь для структурированного JSON находок (для страницы /checks)")
    args = parser.parse_args()

    helper = ProductionHelper(MOYSKLAD_TOKEN)
    monitor = ReturnsMonitor(helper, dry_run=args.dry_run)

    if args.force:
        print(f"[--force] Сброс state, проверяем всё с {START_DATE}")
        monitor.state = {
            "last_run": START_DATE,
            "processed_orders": {}
        }

    if args.daemon:
        print(f"{'='*60}")
        print(f"  Монитор возвратов ВБ/Озон — ЗАПУЩЕН")
        print(f"  Дата старта:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Интервал:     {args.interval} сек ({args.interval//60} мин)")
        print(f"  Агенты:       {', '.join(TARGET_AGENTS)}")
        print(f"  Стартовая дата фильтра: {monitor.state.get('last_run')}")
        print(f"  Dry-run:      {'ДА (документы не создаются)' if args.dry_run else 'НЕТ (реальный режим)'}")
        print(f"{'='*60}")
        print("Для остановки: Ctrl+C  |  Лог пишется сюда же")
        print()

        iteration = 0
        while True:
            iteration += 1
            try:
                monitor.run_once()
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR (итерация {iteration}): {e}")
                print(f"  Следующая попытка через {args.interval} сек...")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Сон {args.interval} сек до следующей проверки...")
            time.sleep(args.interval)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Просыпаемся, итерация {iteration + 1}")
    else:
        counts, details = monitor.run_once()
        if args.results_out:
            try:
                _export_results(counts, details, args.results_out)
            except Exception as e:
                print(f"Ошибка сохранения результатов JSON: {e}")


if __name__ == "__main__":
    main()
