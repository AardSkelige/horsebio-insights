"""
Общие функции для обработки email-заказов сайта horse-bio.ru.

Используется из:
- 01_daemons/06_order_email_sync/scripts/01_read_order_emails.py (чтение почты)
- 01_daemons/06_order_email_sync/scripts/02_create_orders.py (заведение в МойСклад)
- backend/api/views/site_orders.py (страница «Заказы сайта», read-only)
"""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def state_lock(state_file: Path):
    """Эксклюзивная блокировка на весь цикл load→process→save state-файла.

    01_read_order_emails.py и 02_create_orders.py — два независимых процесса,
    оба каждые 5 минут читают один и тот же .order_email_state.json, правят
    и переписывают его целиком. Без лока при неудачном стечении времени тот,
    кто сохраняет вторым, затирает файл своей (более старой) копией — и только
    что записанный другим процессом заказ бесследно исчезает, хотя JSON
    остаётся валидным (см. инцидент с заказом 532598916, 21.07.2026). Лок
    держит файл занятым на всё время работы одного процесса — второй просто
    ждёт своей очереди перед чтением.
    """
    state_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_file.with_name(state_file.name + ".lock")
    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def load_state(state_file: Path, default: dict) -> dict:
    """Вызывать только внутри state_lock()."""
    if state_file.exists():
        return json.loads(state_file.read_text())
    return dict(default)


def save_state(state_file: Path, state: dict):
    """Пишем во временный файл рядом и атомарно переименовываем (os.replace) —
    так процесс, упавший на середине записи, не оставит битый или пустой JSON.
    Вызывать только внутри state_lock()."""
    tmp_path = state_file.with_name(f"{state_file.name}.tmp-{os.getpid()}")
    tmp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str))
    os.replace(tmp_path, state_file)


def build_customer_name(latest: dict) -> str:
    """Собрать ФИО покупателя из полей письма (field:familia/fio/otcestvo)"""
    field = latest.get("field") or {}
    parts = [field.get("familia", "").strip(), field.get("fio", "").strip(), field.get("otcestvo", "").strip()]
    return " ".join(p for p in parts if p)


def format_money(value) -> str:
    """4903 -> '4 903 ₽' — для компактных находок на странице /checks"""
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    return f"{n:,.0f}".replace(",", " ") + " ₽"


def format_phone(raw: str) -> str:
    """+7XXXXXXXXXX -> '+7 999 123-45-67' — для отображения в находках на /checks.
    Формат ввода зеркалит normalize_phone() из 02_create_orders.py, но здесь только
    для человека: если номер нестандартный, просто возвращаем как есть, не роняем."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if len(digits) > 11:
        digits = digits[:11]
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11:
        return f"+{digits[0]} {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return (raw or "").strip()


def build_order_label(latest: dict) -> str:
    """ФИО + номер заказа на сайте — заголовок находки на /checks вместо голого order_id"""
    name = build_customer_name(latest) or "Без имени"
    number = (latest.get("number") or "").strip()
    return f"{name} — №{number}" if number else name


def build_order_delete_action(order_id: str, label: str) -> dict:
    """Данные для кнопки «Удалить» в находке на /checks — убирает запись только
    из нашего журнала (state-файла), письмо и документы в МойСклад не трогает."""
    return {
        "url": f"/site-orders/{order_id}/",
        "confirm": f"Удалить «{label}» из журнала автоматизации? Само письмо и документы "
                   f"в МойСклад (если уже созданы) не тронутся — сотрётся только запись "
                   f"в нашем внутреннем учёте, и при следующей проверке почты письмо "
                   f"может быть разобрано заново.",
    }
