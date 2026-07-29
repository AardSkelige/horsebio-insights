"""Адаптер расчёта тарифа СДЭК поверх существующего CdekClient.

CdekClient (moysklad/horsebio/_shared) уже используется в проде для накладных —
переиспользуем его OAuth и добавленный метод calculate_tarifflist. Отправитель
по умолчанию — наш город (Химки), получатель задаёт оператор.

Два режима под UI: склад→ПВЗ (тариф «посылка склад-склад») и курьер до двери
(тариф «посылка склад-дверь»). Забор курьером от нас не используем — сдаём груз
в пункт СДЭК сами, поэтому сторона отправителя всегда «склад».
"""

import os
import sys

from .box_catalog import Box
from .packing import PackResult

# CdekClient лежит в moysklad/horsebio/_shared — тот же приём, что в api/views/site_orders.py
_SHARED = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                       "moysklad", "horsebio", "_shared")
sys.path.insert(0, _SHARED)
from cdek_client import CdekClient, CdekError  # noqa: E402

# Город отправления HorseBio (сдаём груз в пункт СДЭК сами).
DEFAULT_FROM_CITY = "Химки"

# Коды тарифов СДЭК для наших двух режимов (отправитель — склад/пункт).
TARIFF_WAREHOUSE = 136  # посылка склад→склад (до ПВЗ получателя)
TARIFF_DOOR = 137       # посылка склад→дверь (курьер получателю)


def _packages(result: PackResult) -> list[dict]:
    """Каждая коробка раскладки → грузовое место СДЭК: вес (г) + ШГВ (см, целые)."""
    packages = []
    for pb in result.boxes:
        box: Box = pb.box
        l, w, h = box.dims_cm
        packages.append({
            "weight": int(round(pb.weight_g)),
            "length": int(round(l)),
            "width": int(round(w)),
            "height": int(round(h)),
        })
    return packages


def _tariff_sum(tariffs: list[dict], code: int) -> tuple[float, str] | None:
    """Стоимость и срок по конкретному коду тарифа из ответа tarifflist."""
    for t in tariffs:
        if t.get("tariff_code") == code:
            days = f"{t.get('period_min')} - {t.get('period_max')}"
            return round(float(t.get("delivery_sum") or 0), 2), days
    return None


def calculate(result: PackResult, to_city: str, from_city: str = DEFAULT_FROM_CITY,
              client: CdekClient | None = None) -> dict:
    """Стоимость доставки СДЭК для готовой раскладки.

    Возвращает {'warehouse': ₽ до ПВЗ, 'door': ₽ курьером, 'days': срок} либо
    {'error': ...}."""
    if not result.boxes:
        return {"error": "нет грузовых мест для расчёта"}
    try:
        client = client or CdekClient()
        from_code = client.get_city_code(from_city)
        to_code = client.get_city_code(to_city)
        if from_code is None:
            return {"error": f"город отправления не найден в СДЭК: {from_city!r}"}
        if to_code is None:
            return {"error": f"город назначения не найден в СДЭК: {to_city!r}"}

        data = client.calculate_tarifflist(from_code, to_code, _packages(result))
        tariffs = data.get("tariff_codes") or []
        warehouse = _tariff_sum(tariffs, TARIFF_WAREHOUSE)
        door = _tariff_sum(tariffs, TARIFF_DOOR)
        if warehouse is None and door is None:
            return {"error": "СДЭК не вернул нужные тарифы", "raw": data}

        return {
            "warehouse": warehouse[0] if warehouse else None,
            "door": door[0] if door else None,
            "days": (warehouse or door)[1],
            "to_city_code": to_code,
        }
    except CdekError as e:
        return {"error": f"СДЭК: {e}"}
