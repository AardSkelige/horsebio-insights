"""Накладные СДЭК: правила доставки и разбор адреса получателя.

Отдельно от 01_create_waybills.py по двум причинам: имя того файла начинается с
цифры и не импортируется, а сам он тянет api_client, которому нужен
MOYSKLAD_TOKEN — в CI его нет. Здесь только чистая логика, накрытая тестами
(api/tests/test_cdek_waybills.py).

Способ доставки сайт не передаёт — в письме о заказе всегда просто «СДЭК», —
поэтому читаем его из адреса и текста заказа, см. resolve_delivery().
"""

import re

# Пометки в комментарии заказа, которыми управляет робот (успех/трек/причина).
MARKER_PREFIX = "Накладная СДЭК №"
REASON_MARKER_PREFIX = "⚠ Накладная СДЭК не создана:"
TRACK_LINE_PREFIX = "Отслеживание: https://www.cdek.ru"

# Первый токен адреса доставки — код ПВЗ СДЭК (латиница + цифры), напр. MSK2323
PVZ_CODE_RE = re.compile(r"^\s*([A-Z]{2,5}\d+)\b")
# Явная пометка «пункт выдачи» в тексте заказа: так менеджеры отмечают способ
# доставки при ручном заведении («СДЭК ПВЗ», «СДЭК КУРЬЕР»).
PVZ_WORD_RE = re.compile(r"ПВЗ|ПУНКТ\s+ВЫДАЧИ", re.I)

# Служебные сегменты адреса, которые не могут быть городом
POSTAL_CODE_RE = re.compile(r"^\d{6}$")
CITY_PREFIX_RE = re.compile(
    r"^(?:г\.?|город|пос\.?|пгт|посёлок|поселок|рп|р\.?\s*п\.?|с\.?|село|"
    r"ст-ца|станица|д\.?|деревня)\s+", re.I)
COUNTRY_SEGMENTS = {"россия", "рф"}

PVZ_WITHOUT_CODE_REASON = (
    "указан пункт выдачи, но в адресе нет его кода СДЭК (напр. «MSK2323, Москва, …») "
    "— впишите код ПВЗ или замените пометку на «СДЭК КУРЬЕР»")


def is_managed_line(line: str) -> bool:
    """Строка комментария, которую пишет сам робот (успех/трек/причина)."""
    s = line.strip()
    return (s.startswith(MARKER_PREFIX)
            or s.startswith(REASON_MARKER_PREFIX)
            or s.startswith(TRACK_LINE_PREFIX))


def delivery_text(order: dict) -> str:
    """Текст заказа, в котором менеджер пишет способ доставки.

    Свои строки выбрасываем: в причине «не создана» тоже написано «ПВЗ», и,
    прочитав её на следующем прогоне, робот блокировал бы заказ вечно — даже
    после правки менеджера."""
    saf = order.get("shipmentAddressFull") or {}
    own = [ln for ln in (order.get("description") or "").split("\n")
           if not is_managed_line(ln)]
    return " ".join(own) + " " + (saf.get("comment") or "")


def to_location_candidates(address: str) -> list:
    """Варианты to_location для курьерской доставки — от точного к общему.

    Строку целиком СДЭК геокодит буквально, поэтому сначала пробуем отдать индекс
    или город отдельным полем — так адрес распознаётся даже с опечаткой в улице
    («Мневники» вместо «Мнёвники»)."""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    meaningful = [p for p in parts
                  if not POSTAL_CODE_RE.match(p) and p.lower() not in COUNTRY_SEGMENTS]
    candidates = []

    index = next((p for p in parts if POSTAL_CODE_RE.match(p)), None)
    if index:
        candidates.append({"postal_code": index,
                           "address": ", ".join(meaningful) or address})
    if meaningful:
        city = CITY_PREFIX_RE.sub("", meaningful[0]).strip()
        rest = ", ".join(meaningful[1:])
        if city and rest:
            candidates.append({"city": city, "address": rest})

    candidates.append({"address": address})
    return candidates


def resolve_delivery(address: str, order_text: str, package: dict, location_error):
    """Куда и каким тарифом везём → ("pvz", код) | ("courier", to_location) |
    ("blocked", причина).

    Правило (сайт способа доставки не даёт, поэтому смотрим на данные заказа):
      • адрес начинается с кода ПВЗ — пункт выдачи;
      • кода нет, а в заказе написано «ПВЗ» — блокируем: вместо пункта выдачи
        нельзя молча отправить курьера;
      • кода нет и про ПВЗ ничего не сказано — курьер по адресу.

    location_error(to_location, packages) — проверка локации в СДЭК (обычно
    CdekClient.location_error). Проверяем ДО создания заказа, иначе СДЭК копит
    заказы «Некорректный», по которым накладной не будет никогда."""
    pvz = PVZ_CODE_RE.match(address)
    if pvz:
        return "pvz", pvz.group(1)
    if PVZ_WORD_RE.search(order_text):
        return "blocked", PVZ_WITHOUT_CODE_REASON

    last_error = None
    for candidate in to_location_candidates(address):
        last_error = location_error(candidate, [package])
        if last_error is None:
            return "courier", candidate
    return "blocked", f"СДЭК не распознал адрес «{address}»: {last_error}"
