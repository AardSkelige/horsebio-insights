import re
from decimal import Decimal, ROUND_HALF_UP

def extract_volume(text):
    text = str(text or "").lower().replace("\u00a0", " ").replace(",", ".")
    liters = re.search(r"(\d+(?:\.\d+)?)\s*(?:л|l|литр(?:а|ов)?)\b", text, re.I)
    if liters:
        value = float(liters.group(1)) * 1000
        return int(value) if value.is_integer() else value
    kg = re.search(r"(\d+(?:\.\d+)?)\s*(?:кг|kg)\b", text, re.I)
    if kg:
        value = float(kg.group(1)) * 1000
        return int(value) if value.is_integer() else value
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:мл|ml|г|РјР»|Рі)\b", text, re.I)
    if not match:
        return None
    value = float(match.group(1))
    return int(value) if value.is_integer() else value


def extract_package_count(text):
    text = str(text or "").lower().replace("\u00a0", " ")
    matches = re.findall(r"(\d[\d\s]*)\s*(?:шт|pcs)\.?\b", text, re.I)
    if not matches:
        return None
    return int(matches[-1].replace(" ", ""))


def label_match_norm(text):
    text = str(text or "").lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text, flags=re.I)
    return " ".join(text.split())


def metadata_value(value):
    raw = " ".join(str(value or "").replace("\u00a0", " ").split())
    normalized = label_match_norm(raw)
    if normalized in {"", "б с", "бс", "нет", "не указано", "не указан", "не указана"}:
        return ""
    if raw in {"-", "—", "–"}:
        return ""
    return raw


def producer_series_text(manufacturer, series):
    manufacturer = metadata_value(manufacturer)
    series = metadata_value(series)
    if manufacturer and series:
        return f"{manufacturer} партия № {series}"
    if manufacturer:
        return f"{manufacturer} Б/С"
    if series:
        return series
    return "—"


def pack_amount(text):
    text = str(text or "").lower().replace("\u00a0", " ").replace(",", ".")
    match = re.search(r"\d+(?:[ .]\d+)?", text)
    if not match:
        return None
    raw = match.group(0).replace(" ", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return int(value) if value.is_integer() else value


def row_match_tokens(text):
    text = label_match_norm(text)
    ignored = {"для", "на", "с", "со", "и", "шт", "г", "мл", "продукции"}
    return {token for token in text.split() if token not in ignored and not token.isdigit()}


def animal_of(text):
    norm = label_match_norm(text)
    if "лошад" in norm:
        return "horse"
    if "собак" in norm or "кош" in norm:
        return "dog"
    return ""


def is_mixed_hondrofit(products):
    animals = {animal_of(row.get("source_name") or "") for row in products or []}
    animals.discard("")
    return animals == {"dog", "horse"} and any(
        "хондрофит" in label_match_norm(row.get("source_name") or "")
        for row in products or []
    )


def uses_dispenser(text):
    norm = label_match_norm(text)
    return "дозатор" in norm or "помп" in norm


def task_quantities_equal(left, right):
    try:
        return abs(float(left) - float(right)) < 0.000001
    except (TypeError, ValueError):
        return False


def packaging_container_kind(text):
    norm = label_match_norm(text)
    container_words = ("флакон", "бутыл", "пузыр", "банка", "ведро", "дой пак", "пакет", "мешок", "туб", "канистр", "контейнер", "пробник")
    has_container = any(word in norm for word in container_words)
    accessory_words = ("крышк", "ложк", "помп", "пипет", "распыл", "дозатор")
    if norm.startswith(accessory_words):
        return ""
    if any(word in norm for word in accessory_words) and not has_container:
        return ""
    if "пробник" in norm:
        return "sample"
    if "дой пак" in norm or "пакет" in norm or "мешок" in norm:
        return "bag"
    if "флакон" in norm or "бутыл" in norm or "пузыр" in norm:
        return "bottle"
    if "банка" in norm:
        return "jar"
    if "ведро" in norm:
        return "bucket"
    if "туб" in norm:
        return "tube"
    if "канистр" in norm:
        return "canister"
    if "контейнер" in norm:
        return "container"
    return ""


def is_two_neck_packaging(text):
    norm = label_match_norm(text)
    raw = str(text or "").lower()
    return "2х" in raw or "2x" in raw or "двугорл" in norm or "двухгорл" in norm


def best_label_for_row(row_text, labels, used_indexes, target_volume=None, target_measure_supplied=False):
    row_norm = label_match_norm(row_text)
    row_volume = target_volume
    if row_volume is None and not target_measure_supplied:
        row_volume = extract_volume(row_text)
    row_animal = animal_of(row_text)
    row_tokens = row_match_tokens(row_text)
    candidates = []
    for idx, label in enumerate(labels):
        if idx in used_indexes:
            continue
        label_name = label.get("source_name") or ""
        packaging_name = label.get("packaging_name") or ""
        label_norm = label_match_norm(label_name)
        label_volume = extract_volume(label_name)
        if label_volume is None:
            label_volume = extract_package_count(label_name)
        label_animal = animal_of(label_name)
        if row_volume is not None:
            if label_volume is None or row_volume != label_volume:
                continue
        packaging_match = False
        packaging_compatible = False
        if packaging_name:
            packaging_kind = packaging_container_kind(packaging_name)
            row_kind = packaging_container_kind(row_text)
            packaging_volume = extract_volume(packaging_name)
            if packaging_kind and row_kind != packaging_kind:
                continue
            if packaging_volume is not None and row_volume != packaging_volume:
                continue
            packaging_compatible = True
            packaging_match = (
                uses_dispenser(row_text) == uses_dispenser(packaging_name)
                and is_two_neck_packaging(row_text) == is_two_neck_packaging(packaging_name)
            )
        if not packaging_match and row_animal and label_animal and row_animal != label_animal:
            continue
        label_tokens = row_match_tokens(label_name)
        candidates.append((
            packaging_match,
            packaging_compatible,
            row_norm == label_norm,
            bool(row_animal and label_animal and row_animal == label_animal),
            len(row_tokens & label_tokens),
            idx,
        ))

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][5]
    candidates.sort(reverse=True)
    best = candidates[0]
    second = candidates[1]
    if best[:5] == second[:5]:
        return None
    return best[5] if best[0] or best[1] or best[2] or best[3] or best[4] > 0 else None


def attach_task_packaging_hints(task):
    enriched = dict(task or {})
    products = [dict(row) for row in enriched.get("products") or []]
    labels = [dict(row) for row in enriched.get("labels") or []]
    containers = [
        dict(row)
        for row in enriched.get("materials") or []
        if packaging_container_kind(row.get("source_name") or "")
    ]

    unused = set(range(len(containers)))
    for product in products:
        product_name = product.get("source_name") or ""
        product_volume = extract_volume(product_name)
        matches = []
        for index in unused:
            container = containers[index]
            container_name = container.get("source_name") or ""
            container_volume = extract_volume(container_name)
            if product_volume is None or container_volume != product_volume:
                continue
            if not task_quantities_equal(product.get("qty"), container.get("qty")):
                continue
            matches.append(index)
        if len(matches) == 1:
            selected = matches[0]
            product["packaging_name"] = containers[selected].get("source_name") or ""
            unused.remove(selected)

    for label in labels:
        label_name = label.get("source_name") or ""
        label_volume = extract_volume(label_name)
        label_animal = animal_of(label_name)
        matches = []
        for product in products:
            packaging_name = product.get("packaging_name") or ""
            if not packaging_name or not task_quantities_equal(label.get("qty"), product.get("qty")):
                continue
            product_name = product.get("source_name") or ""
            if label_volume is not None and extract_volume(product_name) != label_volume:
                continue
            product_animal = animal_of(product_name)
            if label_animal and product_animal and label_animal != product_animal:
                continue
            matches.append(product)
        if len(matches) == 1:
            label["packaging_name"] = matches[0]["packaging_name"]

    enriched["products"] = products
    enriched["labels"] = labels
    return enriched


def docx_qty_text(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if isinstance(value, (int, float)):
        num = float(value)
    else:
        m = re.search(r"-?\d[\d\s.]*(?:[,.]\d+)?", raw)
        if not m:
            return raw
        text = m.group(0).replace(" ", "").replace("\u00a0", "")
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        elif text.count(".") > 1:
            text = text.replace(".", "")
        try:
            num = float(text)
        except Exception:
            return re.sub(r"[^0-9,.\-]", "", raw)
    if abs(num - round(num)) < 0.000001:
        return str(int(round(num)))
    if abs(num) >= 1:
        rounded = Decimal(str(num)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return format(rounded, "f")
    return f"{num:.6f}".rstrip("0").rstrip(".").replace(".", ",")


def product_display_name(source_name):
    return re.sub(r",?\s*\d+\s*мл\s*$", "", str(source_name or ""), flags=re.I).strip(" ,")


def label_display_name(source_name):
    text = str(source_name or "").strip()
    text = re.sub(r"^(?:наклейка|этикетка)\s+", "", text, flags=re.I).strip(" «»\"")
    return f"Этикетка «{text}»"
