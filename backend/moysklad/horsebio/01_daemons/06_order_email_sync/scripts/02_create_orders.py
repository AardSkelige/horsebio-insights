#!/usr/bin/env python3
"""
Заведение заказов в МойСклад по данным из state-файла (см. 01_read_order_emails.py).

Этап 3 сквозной задачи. Читает data/.order_email_state.json, для каждого
заказа без своего МойСклад-документа создаёт черновик "Заказ покупателя",
а при появлении письма с paid=1 — создаёт "Входящий платёж" и проводит заказ.

Идемпотентность — по своему полю order["ms"] в том же state-файле (пишем
сюда id/имя созданных документов). Дополнительно перед созданием проверяем
в МойСклад filter=externalCode={order_id} — на случай если state потерян.

Если заказ не оплачен 24 часа — черновик автоматически удаляется из МойСклад
(CANCEL_AFTER_HOURS), заказ помечается отменённым в state. Если оплата всё же
приходит позже — заводим заказ заново с нуля (черновик + сразу платёж).

Перед созданием платежа и перед обновлением описания заказа скрипт сверяется
с живым документом в МойСклад — если сотрудник уже сам принял оплату или
отредактировал комментарий вручную, скрипт это не перезаписывает.

Запуск:
  cd 01_daemons/06_order_email_sync/scripts && python3 02_create_orders.py
  python3 02_create_orders.py              # однократный прогон
  python3 02_create_orders.py --daemon     # режим демона (каждые 5 минут)
  python3 02_create_orders.py --dry-run    # пробный прогон без записи в МойСклад
"""

import argparse
import json
import re
import sys
import time
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import ProductionHelper, MOYSKLAD_TOKEN, BASE_URL
from order_email_utils import build_customer_name, build_order_label, build_order_delete_action

STATE_FILE = Path(__file__).parent.parent / "data" / ".order_email_state.json"

# Черновик без оплаты дольше этого срока — удаляется из МойСклад автоматически
CANCEL_AFTER_HOURS = 24


class OrderCreationError(Exception):
    """Не удалось создать заказ — текст исключения сохраняется в ms['last_error']
    для отображения на странице «Заказы сайта»."""

# Фиксированные реквизиты для заказов с сайта horse-bio.ru — подтверждены на живом аккаунте
ORGANIZATION_META = {"meta": {"href": f"{BASE_URL}/entity/organization/1166fd93-2a9a-11f1-0a80-16d1002fa877", "type": "organization", "mediaType": "application/json"}}
STORE_META = {"meta": {"href": f"{BASE_URL}/entity/store/7507005e-266e-11eb-0a80-030b001555bd", "type": "store", "mediaType": "application/json"}}
SALES_CHANNEL_META = {"meta": {"href": f"{BASE_URL}/entity/saleschannel/af781aeb-711c-11f0-0a80-1a56002f3340", "type": "saleschannel", "mediaType": "application/json"}}
DELIVERY_SERVICE_META = {"meta": {"href": f"{BASE_URL}/entity/service/1202f0a0-d0be-11ee-0a80-10f60014c1a9", "type": "service", "mediaType": "application/json"}}

# Доп. поле заказа "Комментарий от покупателя"
CUSTOMER_NOTE_ATTRIBUTE_META = {"meta": {"href": f"{BASE_URL}/entity/customerorder/metadata/attributes/96282b87-b98a-11ef-0a80-038000318cca", "type": "attributemetadata", "mediaType": "application/json"}}


def normalize_phone(raw: str) -> str:
    """8XXXXXXXXXX / +7XXXXXXXXXX / произвольный ввод -> +7XXXXXXXXXX.
    Лишние цифры после основного номера (опечатка, "доб.123" и т.п.) отбрасываем —
    берём первые 11 цифр, если их больше (реальный номер обычно идёт первым)."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) > 11:
        digits = digits[:11]
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    elif digits:
        print(f"    WARNING: телефон {raw!r} в нестандартном формате — сохраняю как есть")
    return f"+{digits}" if digits else ""


def build_delivery_line(latest: dict) -> str:
    delivery_name = (latest.get("delivery_name") or "").strip()
    if not delivery_name:
        return ""
    address = (latest.get("delivery_field", {}).get("Полный адрес доставки") or "").strip()
    return f"Способ доставки: {delivery_name}" + (" ПВЗ" if not address else "")


def build_shipment_comment(latest: dict) -> str:
    """Текст для shipmentAddressFull.comment — это и есть поле "Комментарий" в шапке
    заказа рядом с адресом доставки (НЕ путать с description — тем большим полем
    под таблицей позиций, это два разных API-поля). Способ доставки дублируется
    в обоих местах — так попросил пользователь."""
    return build_delivery_line(latest)


def build_description(latest: dict) -> str:
    lines = []
    delivery_line = build_delivery_line(latest)
    if delivery_line:
        lines.append(delivery_line)
    lines.append("Статус оплаты: " + ("Оплачен" if latest.get("paid") else "Не оплачен"))
    payment_name = (latest.get("payment_name") or "").strip()
    if payment_name:
        lines.append(f"Способ оплаты: {payment_name}")
    contact_pref = (latest.get("field", {}).get("kak_s_vami_udobnee_svazat_sa_") or "").strip()
    if contact_pref:
        lines.append(f"Предпочитаемая связь: {contact_pref}")

    number = (latest.get("number") or "").strip()
    order_id = (latest.get("order_id") or "").strip()
    if number or order_id:
        lines.append(f"Заказ на сайте: №{number} ({order_id})")

    order_link = (latest.get("order_link") or "").strip()
    if order_link:
        lines.append(f"Ссылка на заказ: {order_link}")

    return "\n".join(lines)


class OrderCreator:
    """Заводит заказы покупателей и входящие платежи в МойСклад по state-файлу почты"""

    def __init__(self, helper: ProductionHelper, dry_run: bool = False):
        self.helper = helper
        self.dry_run = dry_run
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if not STATE_FILE.exists():
            raise FileNotFoundError(
                f"Нет state-файла {STATE_FILE} — сначала запустите 01_read_order_emails.py"
            )
        return json.loads(STATE_FILE.read_text())

    def _save_state(self):
        STATE_FILE.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False, default=str)
        )

    # ─── Контрагент ────────────────────────────────────────────────────────

    def _find_counterparty(self, phone: str, email: str) -> dict | None:
        if phone:
            rows = self.helper._get("/entity/counterparty", {"filter": f"phone={phone}"}).get("rows", [])
            if rows:
                return rows[0]
        if email:
            rows = self.helper._get("/entity/counterparty", {"filter": f"email={email}"}).get("rows", [])
            if rows:
                return rows[0]
        return None

    def _find_or_create_counterparty(self, latest: dict) -> dict:
        field = latest.get("field", {})
        phone = normalize_phone(field.get("phone", ""))
        email = (field.get("email") or "").strip()
        address = (latest.get("delivery_field", {}).get("Полный адрес доставки") or "").strip()

        existing = self._find_counterparty(phone, email)
        if existing:
            patch = {}
            if phone and not existing.get("phone"):
                patch["phone"] = phone
            if email and not existing.get("email"):
                patch["email"] = email
            if address and not existing.get("actualAddress"):
                patch["actualAddress"] = address
            if patch and not self.dry_run:
                existing = self.helper._put(f"/entity/counterparty/{existing['id']}", patch)
            elif patch:
                print(f"    [DRY-RUN] дополнил бы контрагента {existing.get('name')}: {patch}")
            return existing

        payload = {
            "name": build_customer_name(latest),
            "companyType": "individual",
        }
        if phone:
            payload["phone"] = phone
        if email:
            payload["email"] = email
        if address:
            payload["actualAddress"] = address

        if self.dry_run:
            print(f"    [DRY-RUN] создал бы контрагента: {payload}")
            return {"meta": {"href": f"{BASE_URL}/entity/counterparty/dry-run", "type": "counterparty", "mediaType": "application/json"}, "name": payload["name"], "id": "dry-run"}

        return self.helper._post("/entity/counterparty", payload)

    # ─── Позиции ───────────────────────────────────────────────────────────

    def _find_product_meta(self, article: str) -> dict | None:
        rows = self.helper._get("/entity/product", {"filter": f"article={article}"}).get("rows", [])
        if not rows:
            return None
        return {"meta": rows[0]["meta"]}

    def _build_positions(self, latest: dict) -> list:
        """Бросает OrderCreationError, если товар не нашёлся — заказ на этой
        итерации не создаём, попытка повторится на следующем прогоне"""
        positions = []
        for item in latest.get("items", []):
            product_meta = self._find_product_meta(item["article"])
            if product_meta is None:
                raise OrderCreationError(f"Артикул «{item['article']}» не найден в МойСклад")
            positions.append({
                "quantity": float(item["quantity"]),
                "price": round(float(item["price"]) * 100),
                "vat": 0,
                "assortment": product_meta,
            })

        delivery_cost = latest.get("delivery_cost") or ""
        if delivery_cost:
            positions.append({
                "quantity": 1,
                "price": round(float(delivery_cost) * 100),
                "vat": 0,
                "assortment": DELIVERY_SERVICE_META,
            })
        return positions

    # ─── Заказ покупателя ──────────────────────────────────────────────────

    def _find_existing_order_meta(self, order_id: str) -> dict | None:
        """Подстраховка на случай потери state — ищем по externalCode напрямую в МойСклад"""
        rows = self.helper._get("/entity/customerorder", {"filter": f"externalCode={order_id}"}).get("rows", [])
        return rows[0] if rows else None

    def _create_draft_order(self, order_id: str, latest: dict) -> dict | None:
        existing = self._find_existing_order_meta(order_id)
        if existing:
            print(f"    WARNING: заказ {order_id} уже есть в МойСклад ({existing.get('name')}) — state был потерян, подхватываю")
            return existing

        positions = self._build_positions(latest)

        payload = {
            "organization": ORGANIZATION_META,
            "agent": self._find_or_create_counterparty(latest),
            "store": STORE_META,
            "salesChannel": SALES_CHANNEL_META,
            "externalCode": order_id,
            "applicable": False,
            "moment": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "description": build_description(latest),
            "positions": positions,
        }
        shipment_address = (latest.get("delivery_field", {}).get("Полный адрес доставки") or "").strip()
        shipment_comment = build_shipment_comment(latest)
        if shipment_address or shipment_comment:
            shipment_address_full = {}
            if shipment_address:
                shipment_address_full["addInfo"] = shipment_address
            if shipment_comment:
                shipment_address_full["comment"] = shipment_comment
            payload["shipmentAddressFull"] = shipment_address_full

        customer_note = (latest.get("field", {}).get("note") or "").strip()
        if customer_note:
            payload["attributes"] = [{**CUSTOMER_NOTE_ATTRIBUTE_META, "value": customer_note}]

        if self.dry_run:
            print(f"    [DRY-RUN] создал бы черновик заказа {order_id}: agent={payload['agent'].get('name')}, "
                  f"позиций={len(positions)}, комментарий={shipment_comment!r}, описание={payload['description']!r}")
            return {"meta": {"href": f"{BASE_URL}/entity/customerorder/dry-run", "type": "customerorder", "mediaType": "application/json"}, "id": "dry-run", "name": "dry-run"}

        result = self.helper._post("/entity/customerorder", payload)
        print(f"    OK: создан черновик заказа {result.get('name')} для order_id={order_id}")
        return result

    def _create_payment_and_apply(self, order_id: str, order_meta: dict, latest: dict, ms: dict) -> dict | None:
        # agent + текущее состояние заказа берём из живого документа в МойСклад —
        # не только ради agent, но и чтобы проверить, не оплатил/отредактировал ли
        # его уже сотрудник вручную (см. модуль docstring)
        order_full = self.helper._get(f"/entity/customerorder/{order_meta['id']}", {"expand": "agent"}) if not self.dry_run else None

        if order_full and (order_full.get("applicable") or (order_full.get("payedSum") or 0) > 0):
            print(f"    OK: заказ {order_id} уже оплачен/проведён в МойСклад (вручную) — платёж не дублирую")
            return {"id": None, "name": None, "paid_externally": True}

        agent_meta = {"meta": order_full["agent"]["meta"]} if order_full else {"meta": {"href": f"{BASE_URL}/entity/counterparty/dry-run"}}
        total_kopecks = round(float(latest.get("total") or 0) * 100)

        payload = {
            "organization": ORGANIZATION_META,
            "agent": agent_meta,
            "sum": total_kopecks,
            "applicable": True,
            "externalCode": f"{order_id}-payment",
            "moment": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operations": [{"meta": order_meta["meta"]}],
        }

        if self.dry_run:
            print(f"    [DRY-RUN] создал бы входящий платёж на {total_kopecks/100} руб. для заказа {order_id} и провёл бы заказ")
            return {"id": "dry-run", "name": "dry-run"}

        payment = self.helper._post("/entity/paymentin", payload)

        order_update = {"applicable": True}
        new_description = build_description(latest)
        if order_full.get("description") == ms.get("last_description_written"):
            order_update["description"] = new_description
        else:
            print(f"    WARNING: комментарий заказа {order_id} отредактирован вручную в МойСклад — не перезаписываю")

        self.helper._put(f"/entity/customerorder/{order_meta['id']}", order_update)
        if "description" in order_update:
            ms["last_description_written"] = new_description

        print(f"    OK: создан платёж {payment.get('name')} и заказ {order_id} проведён")
        return payment

    # ─── Автоотмена неоплаченных черновиков ────────────────────────────────

    def _maybe_cancel_stale_draft(self, order_id: str, ms: dict):
        """Черновик без оплаты дольше CANCEL_AFTER_HOURS — удаляем из МойСклад.
        Заказ остаётся в state с отметкой cancelled_at — если оплата всё же
        придёт позже, run_once заведёт заказ заново с нуля (см. ниже).

        Может бросить исключение (неверный формат created_at, сетевая ошибка
        удаления) — вызывающий код (run_once) обязан оборачивать в try/except,
        чтобы один битый заказ не прерывал обработку остальных."""
        created_at = ms.get("created_at")
        if not created_at:
            return
        age_hours = (datetime.now() - datetime.fromisoformat(created_at)).total_seconds() / 3600
        if age_hours < CANCEL_AFTER_HOURS:
            return

        if self.dry_run:
            print(f"  [DRY-RUN] заказ {order_id}: не оплачен {age_hours:.1f} ч — удалил бы черновик {ms.get('customerorder_name')} из МойСклад")
            return

        print(f"  Заказ {order_id}: не оплачен {age_hours:.1f} ч — удаляю черновик {ms.get('customerorder_name')} из МойСклад")
        try:
            self.helper._delete(f"/entity/customerorder/{ms['customerorder_id']}")
        except Exception as e:
            print(f"    ERROR: не удалось удалить черновик {order_id}: {e}")
            ms["last_error"] = f"Не удалось удалить неоплаченный черновик: {e}"
            ms["last_error_at"] = datetime.now().isoformat()
            return
        ms["cancelled_at"] = datetime.now().isoformat()
        ms["cancel_reason"] = f"Не оплачен {CANCEL_AFTER_HOURS} ч — черновик удалён автоматически"

    # ─── Основной цикл ─────────────────────────────────────────────────────

    def run_once(self):
        print(f"\n{'='*60}")
        print(f"Заведение заказов в МойСклад: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.dry_run:
            print("[DRY-RUN — в МойСклад ничего не пишется]")
        print(f"{'='*60}")

        counts = {"orders_created": 0, "payments_created": 0, "orders_cancelled": 0, "errors": 0}

        for order_id, order in self.state.get("orders", {}).items():
            latest = order.get("latest")
            if not latest:
                continue
            ms = order.setdefault("ms", {})

            # 24ч без оплаты — удаляем черновик (только если ещё не отменён и не оплачен)
            if ms.get("customerorder_id") and not ms.get("cancelled_at") and not latest.get("paid"):
                before = ms.get("cancelled_at")
                try:
                    self._maybe_cancel_stale_draft(order_id, ms)
                except Exception as e:
                    print(f"    ERROR: автоотмена заказа {order_id} упала: {e}")
                    ms["last_error"] = str(e)
                    ms["last_error_at"] = datetime.now().isoformat()
                    counts["errors"] += 1
                if ms.get("cancelled_at") and not before:
                    counts["orders_cancelled"] += 1

            # Оплата пришла уже ПОСЛЕ автоотмены — прошлый черновик удалён, заводим заказ заново с нуля
            if ms.get("cancelled_at") and latest.get("paid") and not ms.get("recreated_after_cancel"):
                print(f"  Заказ {order_id}: оплата пришла после автоотмены — завожу заново")
                ms["recreated_after_cancel"] = True
                for key in ("customerorder_id", "customerorder_meta", "customerorder_name",
                            "last_description_written", "cancelled_at", "cancel_reason"):
                    ms.pop(key, None)

            if "customerorder_id" not in ms:
                print(f"  Заказ {order_id}:")
                try:
                    result = self._create_draft_order(order_id, latest)
                except Exception as e:
                    print(f"    ERROR: не удалось создать заказ {order_id}: {e}")
                    ms["last_error"] = str(e)
                    ms["last_error_at"] = datetime.now().isoformat()
                    counts["errors"] += 1
                    continue

                if not self.dry_run:
                    ms["customerorder_id"] = result["id"]
                    ms["customerorder_name"] = result.get("name")
                    ms["customerorder_meta"] = result["meta"]
                    ms["created_at"] = datetime.now().isoformat()
                    # result — реальный документ МойСклад (свежесозданный или найденный
                    # по externalCode при потере state) — description берём из него, а не
                    # пересобираем заново, иначе при восстановлении по externalCode здесь
                    # окажется не то, что реально записано в документе
                    ms["last_description_written"] = result.get("description", "")
                ms.pop("last_error", None)
                ms.pop("last_error_at", None)
                counts["orders_created"] += 1

            if latest.get("paid") and "payment_id" not in ms and not ms.get("paid_externally") and "customerorder_meta" in ms:
                try:
                    payment = self._create_payment_and_apply(order_id, {"id": ms["customerorder_id"], "meta": ms["customerorder_meta"]}, latest, ms)
                except Exception as e:
                    print(f"    ERROR: не удалось создать платёж для {order_id}: {e}")
                    ms["last_error"] = str(e)
                    ms["last_error_at"] = datetime.now().isoformat()
                    counts["errors"] += 1
                    continue

                ms.pop("last_error", None)
                ms.pop("last_error_at", None)
                if not self.dry_run and payment:
                    if payment.get("paid_externally"):
                        ms["paid_externally"] = True
                    else:
                        ms["payment_id"] = payment["id"]
                        ms["payment_name"] = payment.get("name")
                    ms["paid_at"] = datetime.now().isoformat()
                counts["payments_created"] += 1

        if not self.dry_run:
            self._save_state()

        print(f"\n{'='*60}")
        print("Итого:")
        print(f"  Создано заказов:    {counts['orders_created']}")
        print(f"  Создано платежей:   {counts['payments_created']}")
        print(f"  Отменено (24ч):     {counts['orders_cancelled']}")
        print(f"  Ошибки:             {counts['errors']}")
        print(f"{'='*60}")

        return counts


def _export_results(counts, state, path):
    """Структурированный JSON для страницы /checks: стат-карточки + раскрываемые списки."""
    import json as _json
    from datetime import datetime as _dt

    cr, pc, cn, er = (counts.get(k, 0) for k in ("orders_created", "payments_created", "orders_cancelled", "errors"))
    stats = [
        {"label": "Создано заказов", "value": cr, "tone": "ok" if cr else "neutral"},
        {"label": "Создано платежей", "value": pc, "tone": "ok" if pc else "neutral"},
        {"label": "Отменено (24ч)", "value": cn, "tone": "warning" if cn else "neutral"},
        {"label": "Ошибки", "value": er, "tone": "critical" if er else "neutral"},
    ]

    def build_item(order_id, order, detail, severity):
        latest = order.get("latest") or {}
        ms = order.get("ms") or {}
        label = build_order_label(latest)
        links = []
        site_link = (latest.get("order_link") or "").strip()
        if site_link:
            links.append({"href": site_link, "label": "Заказ на сайте"})
        if ms.get("customerorder_id"):
            links.append({
                "href": f"https://online.moysklad.ru/app/#customerorder/edit?id={ms['customerorder_id']}",
                "label": "МойСклад",
            })
        return {
            "key": order_id, "ms_id": "", "object": label, "severity": severity,
            "detail": detail, "links": links,
            "delete_action": build_order_delete_action(order_id, label),
        }

    def cat(key, title, sev, items):
        return {"key": key, "title": title, "severity": sev, "kind": None, "ms_type": None,
                "count": len(items), "items": items} if items else None

    error_items = [
        build_item(oid, o, o["ms"]["last_error"], "critical")
        for oid, o in state.get("orders", {}).items() if o.get("ms", {}).get("last_error")
    ]
    cancelled_items = [
        build_item(oid, o, o["ms"].get("cancel_reason", ""), "warning")
        for oid, o in state.get("orders", {}).items() if o.get("ms", {}).get("cancelled_at")
    ]

    categories = [c for c in [
        cat("errors", "Ошибки заведения", "critical", error_items),
        cat("cancelled", "Отменены (не оплачены 24ч)", "warning", cancelled_items),
    ] if c]

    payload = {
        "generated_at": _dt.now().isoformat(timespec="seconds"), "params": {},
        "summary": {"critical": er, "important": cn, "warnings": 0, "ok": cr + pc, "stats": stats},
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Заведение заказов в МойСклад из state-файла почты")
    parser.add_argument("--daemon", action="store_true", help="Запустить как демон")
    parser.add_argument("--interval", type=int, default=300, help="Интервал в секундах (по умолчанию 300)")
    parser.add_argument("--dry-run", action="store_true", help="Пробный прогон без записи в МойСклад")
    parser.add_argument("--results-out", type=str, default=None,
                        help="Путь для структурированного JSON находок (для страницы /checks)")
    args = parser.parse_args()

    helper = ProductionHelper(MOYSKLAD_TOKEN)
    creator = OrderCreator(helper, dry_run=args.dry_run)

    if args.daemon:
        print(f"{'='*60}")
        print("  Заведение заказов в МойСклад — ЗАПУЩЕНО")
        print(f"  Интервал: {args.interval} сек ({args.interval//60} мин)")
        print(f"  Dry-run:  {'ДА' if args.dry_run else 'НЕТ'}")
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
        counts = creator.run_once()
        if args.results_out:
            try:
                _export_results(counts, creator.state, args.results_out)
            except Exception as e:
                print(f"Ошибка сохранения результатов JSON: {e}")


if __name__ == "__main__":
    main()
