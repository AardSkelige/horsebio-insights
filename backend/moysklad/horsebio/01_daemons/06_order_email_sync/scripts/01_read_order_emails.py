#!/usr/bin/env python3
"""
Чтение почты info@horse-bio.ru (mail.ru IMAP) и разбор скрытого блока
HB_ORDER_DATA из писем-уведомлений о заказах Megagroup CMS.

Этап 2 сквозной задачи "заведение заказов в МойСклад по email". МойСклад
здесь не трогаем — только IMAP, парсинг, запись распарсенных заказов
в стейт-файл. Заведение заказов в МойСклад — отдельный этап 3.

Письма в ящике не трогаем: читаем через BODY.PEEK (не выставляет \\Seen),
ничего не помечаем и не перемещаем. Идемпотентность — через собственный
стейт-файл, ключ конкретного письма — Message-ID (стабилен, в отличие от
IMAP UID он не зависит от UIDVALIDITY). order_id из блока HB_ORDER_DATA —
ключ группировки писем одного заказа между собой (на один заказ приходит
несколько писем по мере смены статуса).

Запуск:
  cd 01_daemons/06_order_email_sync/scripts && python3 01_read_order_emails.py
  python3 01_read_order_emails.py              # однократная проверка
  python3 01_read_order_emails.py --daemon     # режим демона (каждые 5 минут)
  python3 01_read_order_emails.py --dry-run    # пробный прогон без записи state
  python3 01_read_order_emails.py --force      # перечитать всю папку заново
"""

import argparse
import base64
import email
import imaplib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from email.header import decode_header
from email.message import Message
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[5] / '.env')

IMAP_HOST = os.getenv('ORDER_MAIL_IMAP_HOST')
IMAP_USER = os.getenv('ORDER_MAIL_IMAP_USER')
IMAP_PASSWORD = os.getenv('ORDER_MAIL_IMAP_PASSWORD')

STATE_FILE = Path(__file__).parent.parent / "data" / ".order_email_state.json"

# Отправитель писем-уведомлений Megagroup CMS — подтверждено на живом письме
NOTIFICATION_SENDER = "noreply@megagroup.ru"

# В ящике настроено правило почты, которое уносит уведомления Megagroup из INBOX
# в отдельные папки (подтверждено на живом ящике 20.07.2026): новые заказы попадают
# в «ЗАКАЗЫ», письма об оплате — в «ОПЛАТА». INBOX всё равно проверяем — на случай,
# если правило когда-нибудь изменится или отключится.
ORDER_FOLDERS = ["INBOX", "ЗАКАЗЫ", "ОПЛАТА"]

# Мониторинг начинается с этой даты — не пытаемся оживить историю заказов за
# прошлые годы (папка «ЗАКАЗЫ» на живом ящике содержит тысячи писем за много лет,
# в основном не про заказы вообще — без даты-фильтра IMAP SEARCH возвращал бы всю
# историю на КАЖДОМ прогоне каждые 5 минут). См. паттерн START_DATE в 03_returns.
HISTORY_START_DATE = "2026-07-20"


def imap_utf7_encode(name: str) -> str:
    """Кодирует имя папки в modified UTF-7 (RFC 3501) — так IMAP-серверы (в т.ч.
    mail.ru/VK WorkSpace) называют папки с кириллицей во внутреннем протоколе.
    '/' и обычная ASCII-часть остаются как есть, кириллица уходит в &...-блок."""
    res = []
    i, n = 0, len(name)
    while i < n:
        c = name[i]
        if 0x20 <= ord(c) <= 0x7e and c != "&":
            res.append(c)
            i += 1
        elif c == "&":
            res.append("&-")
            i += 1
        else:
            j = i
            while j < n and not (0x20 <= ord(name[j]) <= 0x7e):
                j += 1
            chunk = name[i:j].encode("utf-16-be")
            b64 = base64.b64encode(chunk).decode("ascii").rstrip("=").replace("/", ",")
            res.append(f"&{b64}-")
            i = j
    return "".join(res)

HB_BLOCK_RE = re.compile(r"<!--HB_ORDER_DATA(.*?)HB_ORDER_DATA-->", re.DOTALL)

# Ссылка на страницу заказа для покупателя — лежит в видимой части письма (не в HB_ORDER_DATA),
# содержит одноразовый hash-токен доступа без логина
ORDER_LINK_RE = re.compile(r'https://[^\s"\'<>]+/shop/orders\?order_id=\d+[^\s"\'<>]*')


def extract_order_link(html: str) -> str:
    match = ORDER_LINK_RE.search(html)
    return match.group(0) if match else ""


def _decode_mime_words(value: str) -> str:
    """Декодировать MIME-encoded заголовок (=?utf-8?B?...?=) в читаемую строку"""
    if not value:
        return ""
    parts = decode_header(value)
    result = []
    for text, enc in parts:
        if isinstance(text, bytes):
            result.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(text)
    return "".join(result)


def _extract_html_part(msg: Message) -> str | None:
    """Найти и декодировать text/html часть письма"""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return None


def parse_hb_order_data(html: str) -> dict | None:
    """
    Разобрать блок <!--HB_ORDER_DATA ... HB_ORDER_DATA--> в словарь.

    Формат — построчно ключ=значение. Первая строка после открывающего тега —
    пояснительный текст на русском без "=", её пропускаем. Строки
    item~~артикул~~название~~количество~~цена собираются в список items.
    field:* и delivery_field:* уходят в отдельные под-словари.
    """
    match = HB_BLOCK_RE.search(html)
    if not match:
        return None

    data = {
        "field": {},
        "delivery_field": {},
        "items": [],
    }

    for line in match.group(1).splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("item~~"):
            parts = line.split("~~")
            if len(parts) != 5:
                continue
            _, article, name, quantity, price = parts
            data["items"].append({
                "article": article,
                "name": name,
                "quantity": quantity,
                "price": price,
            })
            continue

        if "=" not in line:
            # Пояснительная строка ("Скрытый блок для автоматического...") — пропускаем
            continue

        key, _, value = line.partition("=")

        if key.startswith("field:"):
            data["field"][key[len("field:"):]] = value
        elif key.startswith("delivery_field:"):
            data["delivery_field"][key[len("delivery_field:"):]] = value
        else:
            data[key] = value

    if "order_id" not in data:
        return None

    data["paid"] = data.get("paid") == "1"
    return data


class OrderEmailReader:
    """Читает почту info@horse-bio.ru, разбирает HB_ORDER_DATA, копит state"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
        return {
            "processed_message_ids": [],
            "orders": {},
        }

    def _save_state(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False, default=str)
        )

    def _connect(self) -> imaplib.IMAP4_SSL:
        if not (IMAP_HOST and IMAP_USER and IMAP_PASSWORD):
            raise ValueError(
                "ORDER_MAIL_IMAP_HOST/USER/PASSWORD не заданы в .env"
            )
        conn = imaplib.IMAP4_SSL(IMAP_HOST)
        conn.login(IMAP_USER, IMAP_PASSWORD)
        return conn

    def _select_folder(self, conn: imaplib.IMAP4_SSL, folder: str) -> bool:
        """Возвращает False, если папки не существует (например, правило почты
        поменялось) — тогда просто пропускаем её, не роняя весь прогон."""
        path = folder if folder == "INBOX" else f"INBOX/{folder}"
        status, _ = conn.select(imap_utf7_encode(path), readonly=True)
        return status == "OK"

    def _since_clause(self) -> str:
        """Дата, начиная с которой ищем письма — вчера от last_checked_date (день
        запаса на случай гонки часовых поясов), но не раньше HISTORY_START_DATE."""
        last_checked = self.state.get("last_checked_date") or HISTORY_START_DATE
        d = datetime.strptime(last_checked, "%Y-%m-%d").date() - timedelta(days=1)
        floor = datetime.strptime(HISTORY_START_DATE, "%Y-%m-%d").date()
        if d < floor:
            d = floor
        return d.strftime("%d-%b-%Y")

    def _search_uids(self, conn: imaplib.IMAP4_SSL) -> list[bytes]:
        since = self._since_clause()
        status, data = conn.uid(
            "search", None, f'(FROM "{NOTIFICATION_SENDER}" SINCE {since})'
        )
        if status != "OK":
            raise RuntimeError(f"IMAP SEARCH вернул статус {status}")
        return data[0].split()

    def _fetch_message(self, conn: imaplib.IMAP4_SSL, uid: bytes) -> Message | None:
        # BODY.PEEK[] — не выставляет \Seen, в отличие от RFC822/BODY[]
        status, data = conn.uid("fetch", uid, "(BODY.PEEK[])")
        if status != "OK" or not data or data[0] is None:
            return None
        raw = data[0][1]
        return email.message_from_bytes(raw)

    def _process_message(self, msg: Message, uid: bytes) -> str:
        """
        Обработать одно письмо.
        Returns: 'already_processed' | 'no_html' | 'no_hb_block' | 'recorded' | 'error'
        """
        message_id = msg.get("Message-ID", "").strip()
        if not message_id:
            message_id = f"uid:{uid.decode()}"

        if message_id in self.state["processed_message_ids"]:
            return "already_processed"

        # Письмо инспектировано — независимо от исхода, больше его не трогаем.
        # Иначе не относящиеся к заказам письма от того же отправителя (например,
        # уведомления о модерации комментариев) будут пере-скачиваться каждый прогон.
        if not self.dry_run:
            self.state["processed_message_ids"].append(message_id)

        html = _extract_html_part(msg)
        if html is None:
            print(f"  WARNING: письмо {message_id} без text/html части — пропускаем")
            return "no_html"

        order_data = parse_hb_order_data(html)
        if order_data is None:
            subject = _decode_mime_words(msg.get("Subject", ""))
            print(f"  WARNING: письмо {message_id} ({subject!r}) без блока HB_ORDER_DATA — пропускаем")
            return "no_hb_block"

        order_data["order_link"] = extract_order_link(html)

        order_id = order_data["order_id"]
        snapshot = {
            "message_id": message_id,
            "fetched_at": datetime.now().isoformat(),
            "email_date": msg.get("Date", ""),
            **order_data,
        }

        if self.dry_run:
            paid_label = "оплачен" if order_data["paid"] else "не оплачен"
            print(f"  [DRY-RUN] заказ {order_id} ({paid_label}), позиций: {len(order_data['items'])}")
            return "recorded"

        order_state = self.state["orders"].setdefault(order_id, {"history": [], "latest": None})
        order_state["history"].append(snapshot)
        order_state["latest"] = snapshot

        paid_label = "оплачен" if order_data["paid"] else "не оплачен"
        print(f"  OK: заказ {order_id} — новый снимок ({paid_label}), позиций: {len(order_data['items'])}")
        return "recorded"

    def run_once(self):
        print(f"\n{'='*60}")
        print(f"Проверка почты: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.dry_run:
            print("[DRY-RUN — state не сохраняется]")
        print(f"{'='*60}")

        counts = {
            "already_processed": 0,
            "no_html": 0,
            "no_hb_block": 0,
            "recorded": 0,
            "error": 0,
        }

        conn = self._connect()
        try:
            for folder in ORDER_FOLDERS:
                if not self._select_folder(conn, folder):
                    print(f"  WARNING: папка «{folder}» не найдена в ящике — пропускаю")
                    continue

                uids = self._search_uids(conn)
                print(f"Папка «{folder}»: писем от {NOTIFICATION_SENDER} — {len(uids)}")

                for uid in uids:
                    try:
                        msg = self._fetch_message(conn, uid)
                        if msg is None:
                            print(f"  ERROR: не удалось получить письмо uid={uid.decode()}")
                            counts["error"] += 1
                            continue
                        result = self._process_message(msg, uid)
                        counts[result] += 1
                    except Exception as e:
                        print(f"  ERROR: письмо uid={uid.decode()} — {e}")
                        counts["error"] += 1
        finally:
            conn.logout()

        if not self.dry_run:
            self.state["last_checked_date"] = datetime.now().strftime("%Y-%m-%d")
            self._save_state()

        total_orders = len(self.state["orders"])
        paid_orders = sum(
            1 for o in self.state["orders"].values()
            if o["latest"] and o["latest"].get("paid")
        )

        print(f"\n{'='*60}")
        print("Итого:")
        print(f"  Новых снимков записано:     {counts['recorded']}")
        print(f"  Уже обработаны ранее:       {counts['already_processed']}")
        print(f"  Без HB_ORDER_DATA:          {counts['no_hb_block']}")
        print(f"  Без text/html части:        {counts['no_html']}")
        print(f"  Ошибки:                     {counts['error']}")
        print(f"  Заказов в state всего:      {total_orders} (оплачено: {paid_orders})")
        print(f"{'='*60}")

        return counts, self.state


def _export_results(counts, state, path):
    """Структурированный JSON для страницы /checks: стат-карточки + раскрываемые списки."""
    import json as _json
    from datetime import datetime as _dt

    rec, nb, nh, er = (
        counts.get(k, 0) for k in ("recorded", "no_hb_block", "no_html", "error")
    )
    # already_processed (сколько писем демон уже дедуплицировал) сюда намеренно
    # не выводим — это чисто техническая деталь реализации, для бизнес-пользователя
    # ничего не значит и растёт бесконечно с историей ящика, только запутывает
    # пустой прогон, в котором ничего нового не произошло.
    stats = [
        {"label": "Новых заказов распознано", "value": rec, "tone": "ok" if rec else "neutral"},
        # Не проблема — это письма от того же адреса, но не про заказ (например,
        # уведомление о модерации комментария на сайте). tone нейтральный специально,
        # чтобы не пугать оранжевым цветом то, что нормально происходит каждый прогон.
        {"label": "Другие письма (не про заказ)", "value": nb + nh, "tone": "neutral"},
        {"label": "Ошибки разбора", "value": er, "tone": "critical" if er else "neutral"},
    ]

    recorded_orders = []
    for order_id, order in state.get("orders", {}).items():
        latest = order.get("latest")
        if not latest:
            continue
        recorded_orders.append({
            "key": "", "ms_id": "", "object": f"Заказ №{order_id}",
            "severity": "ok",
            "detail": f"{'оплачен' if latest.get('paid') else 'не оплачен'} · "
                      f"{latest.get('total', '?')} {latest.get('currency', '')} · "
                      f"позиций: {len(latest.get('items', []))}",
        })

    categories = []
    if recorded_orders:
        categories.append({
            "key": "orders", "title": "Заказы в state", "severity": "ok",
            "kind": None, "ms_type": None,
            "count": len(recorded_orders), "items": recorded_orders,
        })

    payload = {
        "generated_at": _dt.now().isoformat(timespec="seconds"), "params": {},
        # important/warnings оставляем 0: "другие письма" — не проблема, а норма,
        # не должна зажигать оранжевый бейдж "N проблема" на общем экране /checks
        "summary": {"critical": er, "important": 0, "warnings": 0, "ok": rec, "stats": stats},
        "categories": categories,
    }
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Чтение почты info@horse-bio.ru и разбор HB_ORDER_DATA"
    )
    parser.add_argument("--daemon", action="store_true", help="Запустить как демон")
    parser.add_argument("--interval", type=int, default=300,
                        help="Интервал проверки в секундах (по умолчанию 300)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Пробный прогон без записи в state")
    parser.add_argument("--force", action="store_true",
                        help="Сбросить state и перечитать всю папку заново")
    parser.add_argument("--results-out", type=str, default=None,
                        help="Путь для структурированного JSON находок (для страницы /checks)")
    args = parser.parse_args()

    reader = OrderEmailReader(dry_run=args.dry_run)

    if args.force:
        print("[--force] Сброс state, перечитываем всю папку заново")
        reader.state = {"processed_message_ids": [], "orders": {}}

    if args.daemon:
        print(f"{'='*60}")
        print("  Чтение почты заказов — ЗАПУЩЕНО")
        print(f"  Дата старта:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Интервал:     {args.interval} сек ({args.interval//60} мин)")
        print(f"  Ящик:         {IMAP_USER}")
        print(f"  Dry-run:      {'ДА (state не пишется)' if args.dry_run else 'НЕТ (реальный режим)'}")
        print(f"{'='*60}")
        print("Для остановки: Ctrl+C  |  Лог пишется сюда же")
        print()

        iteration = 0
        while True:
            iteration += 1
            try:
                reader.run_once()
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR (итерация {iteration}): {e}")
                print(f"  Следующая попытка через {args.interval} сек...")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Сон {args.interval} сек до следующей проверки...")
            time.sleep(args.interval)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Просыпаемся, итерация {iteration + 1}")
    else:
        counts, state = reader.run_once()
        if args.results_out:
            try:
                _export_results(counts, state, args.results_out)
            except Exception as e:
                print(f"Ошибка сохранения результатов JSON: {e}")


if __name__ == "__main__":
    main()
