"""
Общие функции для обработки email-заказов сайта horse-bio.ru.

Используется из:
- 01_daemons/06_order_email_sync/scripts/01_read_order_emails.py (чтение почты)
- 01_daemons/06_order_email_sync/scripts/02_create_orders.py (заведение в МойСклад)
- backend/api/views/site_orders.py (страница «Заказы сайта», read-only)
"""


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
