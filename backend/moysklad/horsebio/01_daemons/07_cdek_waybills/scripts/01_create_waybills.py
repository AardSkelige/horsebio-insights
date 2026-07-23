#!/usr/bin/env python3
"""
Автоматическое формирование накладных СДЭК для оплаченных заказов с сайта и
прикрепление PDF к заказу покупателя в МойСклад.

Демон мониторит МойСклад (раз в 5 минут) и для каждого подходящего заказа:
регистрирует отправление в СДЭК → дожидается номера → формирует печатную
форму-квитанцию → скачивает PDF → прикрепляет его к заказу в МойСклад и
помечает заказ (в комментарии), чтобы его больше не трогать.

Подходящий заказ (все условия сразу):
  • канал продаж «Сайт Horse-Bio»;
  • статус «Можно собирать» (робот заведения заказов ставит его при оплате);
  • оплачен (payedSum > 0);
  • доставка СДЭК (по комментарию заказа);
  • ровно одна товарная позиция в количестве 1 шт (пока автоматизируем только
    одиночки — для них однозначно известна упаковка и габариты);
  • ещё нет накладной (нет пометки в комментарии и нет записи в state).

Данные для СДЭК берём целиком из МойСклад: получатель (агент), позиция (артикул,
цена, вес), габариты упаковки — из доп-полей карточки товара. Код ПВЗ получателя
— первым токеном адреса доставки (напр. «MSK2323»); если кода нет — курьерский
тариф по адресу. Отправитель/продавец СДЭК подставляет сам из договора.

Идемпотентность — свой state-файл data/.cdek_waybill_state.json (прогресс по
каждому заказу) + пометка в комментарии заказа + поиск в СДЭК по номеру перед
созданием (чтобы повторный прогон после сбоя не создал дубль отправления).

Запуск:
  cd 01_daemons/07_cdek_waybills/scripts && python3 01_create_waybills.py
  python3 01_create_waybills.py                 # однократный прогон
  python3 01_create_waybills.py --daemon         # режим демона (каждые 5 минут)
  python3 01_create_waybills.py --dry-run        # разбор кандидатов без записи в СДЭК/МойСклад
  python3 01_create_waybills.py --order <ms_id>  # обработать один заказ по id (для отладки)
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import ProductionHelper, MOYSKLAD_TOKEN, BASE_URL
from cdek_client import CdekClient, CdekError

STATE_FILE = Path(__file__).parent.parent / "data" / ".cdek_waybill_state.json"

# ─── Параметры МойСклад (подтверждены на живом аккаунте) ────────────────────
SITE_SALES_CHANNEL_ID = "af781aeb-711c-11f0-0a80-1a56002f3340"   # «Прочее | Сайт Horse-Bio»
STATE_CAN_ASSEMBLE_ID = "50cfc5c8-71b1-11ef-0a80-0218000bda38"   # статус «Можно собирать»
# Доп-поля карточки товара — габариты упаковки в целых см
ATTR_LENGTH_ID = "4810397c-85d2-11f1-0a80-069b00109dbb"
ATTR_WIDTH_ID = "48103da4-85d2-11f1-0a80-069b00109dbc"
ATTR_HEIGHT_ID = "48103faa-85d2-11f1-0a80-069b00109dbd"

# ─── Параметры СДЭК ─────────────────────────────────────────────────────────
SHIPMENT_POINT = "KHME10"       # наш ПВЗ отправления (Химки)
TARIFF_PVZ = 136                # посылка склад-склад (ПВЗ → ПВЗ)
TARIFF_COURIER = 137            # посылка склад-дверь (ПВЗ → курьер)

# Пометки в комментарии заказа — и человеку видно, и служат маркерами состояния.
# Успех: строка с номером накладной (+ трек); служит доп-маркером идемпотентности.
# Причина: почему накладная НЕ создана (не заполнены габариты и т.п.) — чтобы
# сотрудник видел в самом заказе, почему накладной нет. Обе строки — «управляемые»:
# при следующем прогоне они переписываются/снимаются в зависимости от состояния.
MARKER_PREFIX = "Накладная СДЭК №"
REASON_MARKER_PREFIX = "⚠ Накладная СДЭК не создана:"
TRACK_LINE_PREFIX = "Отслеживание: https://www.cdek.ru"
TRACK_URL = "https://www.cdek.ru/ru/tracking?order_id={number}"

# Первый токен адреса доставки — код ПВЗ СДЭК (латиница + цифры), напр. MSK2323
PVZ_CODE_RE = re.compile(r"^\s*([A-Z]{2,5}\d+)\b")


class WaybillError(Exception):
    """Кандидат подходит, но данных не хватает или СДЭК/МойСклад вернули ошибку.
    Текст показываем на странице /checks и сохраняем в state['last_error']."""


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"orders": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    return f"+{digits}" if digits else ""


class WaybillCreator:
    """Формирует накладные СДЭК по подходящим заказам МойСклад."""

    def __init__(self, ms: ProductionHelper, cdek: CdekClient, dry_run: bool = False):
        self.ms = ms
        self.cdek = cdek
        self.dry_run = dry_run
        self.state = {"orders": {}}

    # ─── Выборка кандидатов ─────────────────────────────────────────────────

    def _fetch_candidates(self) -> list:
        """Заказы сайта в статусе «Можно собирать» с раскрытыми позициями и агентом."""
        params = {
            "filter": (
                f"salesChannel={BASE_URL}/entity/saleschannel/{SITE_SALES_CHANNEL_ID};"
                f"state={BASE_URL}/entity/customerorder/metadata/states/{STATE_CAN_ASSEMBLE_ID}"
            ),
            "expand": "positions.assortment,agent",
            "limit": 100,
            "order": "moment,desc",
        }
        return self.ms._get("/entity/customerorder", params).get("rows", [])

    # ─── Разбор одного заказа ───────────────────────────────────────────────

    @staticmethod
    def _product_positions(order: dict) -> list:
        """Товарные позиции без строки услуги «Доставка»."""
        rows = (order.get("positions") or {}).get("rows", [])
        return [p for p in rows if (p.get("assortment") or {}).get("meta", {}).get("type") == "product"]

    @staticmethod
    def _attr(product: dict, attr_id: str):
        for a in product.get("attributes", []):
            if a.get("id") == attr_id:
                return a.get("value")
        return None

    def _delivery_address(self, order: dict) -> str:
        saf = order.get("shipmentAddressFull") or {}
        return (saf.get("addInfo") or order.get("shipmentAddress") or "").strip()

    def _is_cdek_delivery(self, order: dict) -> bool:
        text = (order.get("description") or "")
        saf = order.get("shipmentAddressFull") or {}
        text += " " + (saf.get("comment") or "")
        return "СДЭК" in text or "CDEK" in text.upper()

    def _already_done(self, order_id: str, order: dict) -> bool:
        st = self.state["orders"].get(order_id, {})
        if st.get("pdf_attached"):
            return True
        return MARKER_PREFIX in (order.get("description") or "")

    def classify(self, order: dict):
        """→ (status, detail). status: 'done'|'skip'|'manual'|'ready'.
        'ready' возвращает (('ready'), context) с готовыми данными для СДЭК."""
        order_id = order["id"]

        if not self._is_cdek_delivery(order):
            return "skip", "доставка не СДЭК"
        if (order.get("payedSum") or 0) <= 0:
            return "skip", "не оплачен"
        if self._already_done(order_id, order):
            return "done", "накладная уже есть"

        products = self._product_positions(order)
        if len(products) != 1 or float(products[0].get("quantity") or 0) != 1:
            # Многотоварные заказы — ожидаемо оформляются вручную, это не ошибка.
            # Комментарий заказа не трогаем (иначе засорим большинство заказов).
            return "multi", "не одиночный заказ (несколько товаров или количество > 1)"

        # Дальше — заказ-одиночка, который МЫ должны автоматизировать. Если чего-то
        # не хватает, статус «blocked»: причину пишем в комментарий заказа.
        pos = products[0]
        product = pos.get("assortment") or {}
        weight = product.get("weight")
        length = self._attr(product, ATTR_LENGTH_ID)
        width = self._attr(product, ATTR_WIDTH_ID)
        height = self._attr(product, ATTR_HEIGHT_ID)

        missing = []
        if not weight:
            missing.append("вес")
        if not length or not width or not height:
            missing.append("габариты упаковки (Д/Ш/В)")
        if missing:
            return "blocked", f"в карточке товара «{product.get('name')}» не заполнены: {', '.join(missing)}"

        agent = order.get("agent") or {}
        phone = normalize_phone(agent.get("phone", ""))
        if not phone:
            return "blocked", f"у контрагента «{agent.get('name')}» не указан телефон — обязателен для СДЭК"

        address = self._delivery_address(order)
        if not address:
            return "blocked", "нет адреса доставки в заказе"

        return "ready", {
            "order": order,
            "product": product,
            "position": pos,
            "weight": int(weight),
            "dims": (int(length), int(width), int(height)),
            "agent_name": agent.get("name") or "Покупатель",
            "phone": phone,
            "address": address,
        }

    # ─── Сборка payload СДЭК ────────────────────────────────────────────────

    def build_cdek_order(self, ctx: dict) -> dict:
        order = ctx["order"]
        pos = ctx["position"]
        product = ctx["product"]
        number = (order.get("externalCode") or order.get("name") or order["id"]).strip()

        length, width, height = ctx["dims"]
        cost = round(float(pos.get("price") or 0) / 100, 2)  # цена позиции в рублях

        payload = {
            "type": 1,                       # интернет-магазин
            "number": number,
            "shipment_point": SHIPMENT_POINT,
            "recipient": {
                "name": ctx["agent_name"],
                "phones": [{"number": ctx["phone"]}],
            },
            "packages": [{
                "number": "1",
                "weight": ctx["weight"],
                "length": length, "width": width, "height": height,
                "items": [{
                    "name": product.get("name"),
                    "ware_key": product.get("article") or product.get("code") or number,
                    "amount": 1,
                    "weight": ctx["weight"],
                    "cost": cost,
                    "payment": {"value": 0},   # предоплата — наложенного платежа нет
                }],
            }],
        }

        # Код ПВЗ в адресе → тариф склад-склад; иначе курьер по адресу
        pvz = PVZ_CODE_RE.match(ctx["address"])
        if pvz:
            payload["tariff_code"] = TARIFF_PVZ
            payload["delivery_point"] = pvz.group(1)
        else:
            payload["tariff_code"] = TARIFF_COURIER
            payload["to_location"] = {"address": ctx["address"]}
        return payload

    # ─── Создание накладной по одному заказу ────────────────────────────────

    def process(self, ctx: dict) -> dict:
        """Создаёт заказ СДЭК (или подхватывает существующий), формирует накладную,
        скачивает PDF и прикрепляет к заказу МойСклад. Возвращает info для лога."""
        order = ctx["order"]
        order_id = order["id"]
        st = self.state["orders"].setdefault(order_id, {})
        cdek_order = self.build_cdek_order(ctx)
        number = cdek_order["number"]

        if self.dry_run:
            print(f"  [DRY-RUN] заказ {order.get('name')} ({number}): payload СДЭК:")
            print("    " + json.dumps(cdek_order, ensure_ascii=False, indent=2).replace("\n", "\n    "))
            return {"dry_run": True}

        # 1) Заказ СДЭК: из state, либо ищем по номеру (защита от дублей), либо создаём
        cdek_uuid = st.get("cdek_uuid")
        cdek_number = st.get("cdek_number")
        if not cdek_uuid:
            existing = self.cdek.find_order_by_number(number)
            if existing:
                cdek_uuid = existing["entity"]["uuid"]
                cdek_number = existing["entity"].get("cdek_number")
                print(f"  Заказ {number}: подхватываю уже созданный в СДЭК ({cdek_number})")
            else:
                resp = self.cdek.create_order(cdek_order)
                cdek_uuid = (resp.get("entity") or {}).get("uuid")
                if not cdek_uuid:
                    raise WaybillError(f"СДЭК не вернул uuid заказа: {resp}")
            st["cdek_uuid"] = cdek_uuid
            st["created_at"] = datetime.now().isoformat()

        if not cdek_number:
            info = self.cdek.poll_order(cdek_uuid)
            cdek_number = (info.get("entity") or {}).get("cdek_number")
            st["cdek_number"] = cdek_number
            print(f"  Заказ {number}: номер СДЭК {cdek_number}")

        # 2) Печатная форма → PDF → прикрепление к заказу МойСклад
        if not st.get("pdf_attached"):
            pr = self.cdek.create_waybill(cdek_uuid)
            print_uuid = (pr.get("entity") or {}).get("uuid")
            self.cdek.poll_waybill(print_uuid)
            pdf = self.cdek.download_waybill_pdf(print_uuid)
            filename = f"Накладная СДЭК {cdek_number}.pdf"
            self.ms._post(
                f"/entity/customerorder/{order_id}/files",
                [{"filename": filename, "content": base64.b64encode(pdf).decode()}],
            )
            st["pdf_attached"] = True
            st["print_uuid"] = print_uuid
            print(f"  Заказ {number}: PDF ({len(pdf)} б) прикреплён к заказу МойСклад")

        # 3) Пометка в комментарии заказа — успех (снимает прежнюю причину, если была)
        self._write_order_note(order_id, success_number=cdek_number)

        st.pop("last_error", None)
        st.pop("last_error_at", None)
        return {"cdek_number": cdek_number}

    @staticmethod
    def _is_managed_line(line: str) -> bool:
        """Строки комментария, которыми управляет робот (успех/трек/причина)."""
        s = line.strip()
        return (s.startswith(MARKER_PREFIX)
                or s.startswith(REASON_MARKER_PREFIX)
                or s.startswith(TRACK_LINE_PREFIX))

    def _write_order_note(self, order_id: str, *, success_number: str = None, reason: str = None) -> None:
        """Единая точка правки комментария заказа. Снимает прежние управляемые строки
        и ставит нужную: успех (номер+трек) ИЛИ причину «не создана». Пишем в МойСклад
        только если текст реально изменился — иначе каждый прогон не дёргает заказ.
        Свежий description читаем из МойСклад, чтобы не затереть правку сотрудника."""
        if success_number:
            block = [f"{MARKER_PREFIX}{success_number} — не редактировать заказ",
                     f"Отслеживание: {TRACK_URL.format(number=success_number)}"]
        elif reason:
            block = [f"{REASON_MARKER_PREFIX} {reason}"]
        else:
            block = []

        if self.dry_run:
            print(f"    [DRY-RUN] в комментарий заказа записал бы: {block or '— (снял бы пометки)'}")
            return

        fresh = self.ms._get(f"/entity/customerorder/{order_id}")
        description = fresh.get("description") or ""
        kept = [ln for ln in description.split("\n") if not self._is_managed_line(ln)]
        base = "\n".join(kept).rstrip()
        new_description = "\n".join(([base] if base else []) + block).strip()
        if new_description != description:
            self.ms._put(f"/entity/customerorder/{order_id}", {"description": new_description})

    def _touch(self, order: dict, **fields) -> dict:
        """Обновить запись заказа в state (имя, время, статус/причина) — источник
        для страницы /checks (см. _export_results)."""
        st = self.state["orders"].setdefault(order["id"], {})
        st["name"] = order.get("name")
        st["updated_at"] = datetime.now().isoformat()
        st.update(fields)
        return st

    # ─── Основной цикл ──────────────────────────────────────────────────────

    def run_once(self, single_order_id: str = None):
        print(f"\n{'='*60}")
        print(f"Накладные СДЭК: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
              f"{'  [DRY-RUN]' if self.dry_run else ''}")
        print(f"{'='*60}")

        self.state = load_state()
        counts = {"created": 0, "multi": 0, "blocked": 0, "errors": 0, "done": 0}

        if single_order_id:
            orders = [self.ms._get(f"/entity/customerorder/{single_order_id}",
                                   {"expand": "positions.assortment,agent"})]
        else:
            orders = self._fetch_candidates()
        print(f"Кандидатов на разбор: {len(orders)}")

        for order in orders:
            order_id = order["id"]
            status, detail = self.classify(order)

            if status in ("skip", "done"):
                if status == "done":
                    counts["done"] += 1
                continue

            if status == "multi":
                # Ожидаемо ручной — комментарий и state не трогаем
                counts["multi"] += 1
                continue

            if status == "blocked":
                # Одиночка, но данных не хватает — пишем причину в комментарий заказа
                counts["blocked"] += 1
                print(f"  Заказ {order.get('name')}: не могу создать — {detail}")
                self._touch(order, status="blocked", reason=detail)
                try:
                    self._write_order_note(order_id, reason=detail)
                except Exception as e:
                    print(f"    WARNING: не удалось записать причину в заказ: {e}")
                continue

            # status == 'ready'
            print(f"  Заказ {order.get('name')}: формирую накладную…")
            try:
                self.process(detail)
                if not self.dry_run:
                    counts["created"] += 1
                    self._touch(order, status="created", reason=None)
            except Exception as e:   # один битый заказ не должен ронять весь прогон
                counts["errors"] += 1
                self._touch(order, status="error", last_error=str(e),
                            last_error_at=datetime.now().isoformat())
                print(f"    ERROR: {e}")
                # Причину ошибки тоже показываем в заказе
                try:
                    self._write_order_note(order_id, reason=f"ошибка формирования — {e}")
                except Exception as e2:
                    print(f"    WARNING: не удалось записать ошибку в заказ: {e2}")

        if not self.dry_run:
            save_state(self.state)

        print(f"\n{'='*60}")
        print(f"  Создано накладных:  {counts['created']}")
        print(f"  Не хватает данных:  {counts['blocked']}")
        print(f"  Многотоварные:      {counts['multi']}")
        print(f"  Уже готовы:         {counts['done']}")
        print(f"  Ошибки:             {counts['errors']}")
        print(f"{'='*60}")
        return counts


# Окно, за которое созданные накладные показываются в журнале робота на /checks
RECENT_DAYS = 14


def _ms_order_link(order_id: str) -> dict:
    return {"href": f"https://online.moysklad.ru/app/#customerorder/edit?id={order_id}",
            "label": "МойСклад"}


def _export_results(state: dict, path: str) -> None:
    """Структурированный JSON для страницы /checks: стат-карточки + раскрываемые
    списки. Читаем из state (переживает пустые прогоны — бэкенд мёржит за 14 дней)."""
    from datetime import datetime as _dt, timedelta as _td

    def _in_window(iso: str) -> bool:
        try:
            return _dt.fromisoformat(iso) >= _dt.now() - _td(days=RECENT_DAYS)
        except (ValueError, TypeError):
            return False

    def item(order_id, st, detail, severity):
        return {"key": order_id, "ms_id": order_id,
                "object": f"Заказ {st.get('name') or order_id}", "severity": severity,
                "detail": detail, "links": [_ms_order_link(order_id)]}

    orders = state.get("orders", {})
    error_items, blocked_items, created_items = [], [], []
    for oid, st in orders.items():
        status = st.get("status")
        if status == "error":
            error_items.append(item(oid, st, st.get("last_error", "ошибка"), "critical"))
        elif status == "blocked":
            blocked_items.append(item(oid, st, st.get("reason", "не хватает данных"), "warning"))
        elif status == "created" and _in_window(st.get("updated_at")):
            num = st.get("cdek_number")
            created_items.append(item(oid, st, f"Накладная СДЭК №{num}", "ok"))

    def cat(key, title, sev, items_):
        return {"key": key, "title": title, "severity": sev, "kind": None,
                "ms_type": None, "count": len(items_), "items": items_} if items_ else None

    categories = [c for c in [
        cat("errors", "Ошибки формирования", "critical", error_items),
        cat("blocked", "Не создано — не хватает данных", "warning", blocked_items),
        cat("created", "Накладные созданы", "ok", created_items),
    ] if c]

    stats = [
        {"label": "Накладных создано", "value": len(created_items), "tone": "ok" if created_items else "neutral"},
        {"label": "Не хватает данных", "value": len(blocked_items), "tone": "warning" if blocked_items else "neutral"},
        {"label": "Ошибки", "value": len(error_items), "tone": "critical" if error_items else "neutral"},
    ]
    payload = {
        "generated_at": _dt.now().isoformat(timespec="seconds"), "params": {},
        "summary": {"critical": len(error_items), "important": len(blocked_items),
                    "warnings": 0, "ok": len(created_items), "stats": stats},
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Формирование накладных СДЭК по заказам МойСклад")
    parser.add_argument("--daemon", action="store_true", help="Запустить как демон")
    parser.add_argument("--interval", type=int, default=300, help="Интервал в секундах (по умолчанию 300)")
    parser.add_argument("--dry-run", action="store_true", help="Разбор без записи в СДЭК/МойСклад")
    parser.add_argument("--order", type=str, default=None, help="Обработать один заказ МойСклад по id (отладка)")
    parser.add_argument("--results-out", type=str, default=None,
                        help="Путь для структурированного JSON находок (для страницы /checks)")
    args = parser.parse_args()

    ms = ProductionHelper(MOYSKLAD_TOKEN)
    cdek = CdekClient()
    creator = WaybillCreator(ms, cdek, dry_run=args.dry_run)

    if args.daemon:
        print(f"{'='*60}")
        print("  Накладные СДЭК — ЗАПУЩЕНО")
        print(f"  Интервал: {args.interval} сек ({args.interval//60} мин) | Среда СДЭК: {cdek.env}")
        print(f"{'='*60}")
        iteration = 0
        while True:
            iteration += 1
            try:
                creator.run_once()
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR (итерация {iteration}): {e}")
            time.sleep(args.interval)
    else:
        creator.run_once(single_order_id=args.order)
        if args.results_out:
            try:
                _export_results(creator.state, args.results_out)
            except Exception as e:
                print(f"Ошибка сохранения результатов JSON: {e}")


if __name__ == "__main__":
    main()
