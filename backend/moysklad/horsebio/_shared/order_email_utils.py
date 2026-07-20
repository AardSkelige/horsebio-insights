"""
Общие функции для обработки email-заказов сайта horse-bio.ru.

Используется из:
- 01_daemons/06_order_email_sync/scripts/02_create_orders.py (заведение в МойСклад)
- backend/api/views/site_orders.py (страница «Заказы сайта», read-only)
"""


def build_customer_name(latest: dict) -> str:
    """Собрать ФИО покупателя из полей письма (field:familia/fio/otcestvo)"""
    field = latest.get("field") or {}
    parts = [field.get("familia", "").strip(), field.get("fio", "").strip(), field.get("otcestvo", "").strip()]
    return " ".join(p for p in parts if p)
