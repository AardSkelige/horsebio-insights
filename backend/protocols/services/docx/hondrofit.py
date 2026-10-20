import copy
import re
from pathlib import Path

from .wordml import NS, cells_of, set_text, text_of
from .matching import animal_of, extract_volume, is_mixed_hondrofit, label_display_name, label_match_norm, pack_amount, product_display_name, uses_dispenser
from .tables import replace_table_data_rows

def hondrofit_water_dosages(template_path):
    name = Path(template_path).stem.lower().replace("ё", "е")
    if "хондрофит" in name:
        return (17000, 38410)
    return ()


def mixed_packaging_exemplar(table, volume, dispenser):
    for row in table.findall("./w:tr", NS)[1:]:
        cells = cells_of(row)
        if len(cells) < 3:
            continue
        if pack_amount(text_of(cells[2])) != volume:
            continue
        row_dispenser = uses_dispenser(text_of(cells[0]) + " " + text_of(cells[1]))
        if row_dispenser == dispenser:
            return row
    return None


def mixed_label_exemplar(table, volume, dispenser):
    for row in table.findall("./w:tr", NS)[1:]:
        cells = cells_of(row)
        if len(cells) < 2:
            continue
        if extract_volume(text_of(cells[1])) != volume:
            continue
        row_dispenser = uses_dispenser(text_of(cells[0]) + " " + text_of(cells[1]))
        if row_dispenser == dispenser:
            return row
    return None


def rewrite_combined_hondrofit_title(root, direct_body_only=False):
    root_norm = label_match_norm(text_of(root))
    if "хондрофит" not in root_norm or "для собак" not in root_norm:
        return
    if direct_body_only:
        body = root.find("./w:body", NS)
        paragraphs = [] if body is None else body.findall("./w:p", NS)
    else:
        paragraphs = root.findall(".//w:p", NS)
    for paragraph in paragraphs:
        text = text_of(paragraph)
        norm = label_match_norm(text)
        if "для собак" not in norm:
            continue
        combined = re.sub(r"для\s+собак(?!\s+и\s+лошадей)", "для собак и лошадей", text, flags=re.I)
        if combined != text:
            set_text(paragraph, combined)


def mixed_tare_rows(table, products, packaging_rows, plus):
    source_rows = table.findall("./w:tr", NS)[1:]
    if not source_rows:
        return []

    def clone_with_name(name, predicate=None):
        exemplar = next((row for row in source_rows if predicate and predicate(text_of(row))), source_rows[0])
        row = copy.deepcopy(exemplar)
        cells = cells_of(row)
        set_text(cells[0], name)
        if len(cells) > 1:
            set_text(cells[1], "")
        return row

    rows = []
    seen = set()
    for packaging_row in packaging_rows:
        name = text_of(cells_of(packaging_row)[0]).strip()
        key = label_match_norm(name)
        if not name or key in seen:
            continue
        seen.add(key)
        volume = extract_volume(name)
        dispenser = uses_dispenser(name)
        rows.append(clone_with_name(
            name,
            lambda text, v=volume, d=dispenser: extract_volume(text) == v and uses_dispenser(text) == d,
        ))

    if any(uses_dispenser(row.get("source_name") or "") for row in products):
        pump_name = "Дозатор 24/410 с рифленой юбкой (длина трубки 220мм)"
        rows.append(clone_with_name(pump_name, lambda text: "дозатор 24" in label_match_norm(text)))

    two_neck_products = [
        row for row in products
        if extract_volume(row.get("source_name") or "") in (500, 1000)
        and not uses_dispenser(row.get("source_name") or "")
    ]
    if plus and two_neck_products or any(animal_of(row.get("source_name") or "") == "horse" for row in two_neck_products):
        blue = "Крышка на двугорлую бутылку (синяя)"
        rows.append(clone_with_name(blue, lambda text: "крышка" in label_match_norm(text)))
    if not plus and any(animal_of(row.get("source_name") or "") == "dog" for row in two_neck_products):
        white = "Крышка на двугорлую бутылку (белая)"
        rows.append(clone_with_name(white, lambda text: "крышка" in label_match_norm(text)))
    return rows


def prepare_mixed_hondrofit(document, products, labels):
    if not is_mixed_hondrofit(products):
        return False
    tables = document.findall(".//w:tbl", NS)
    if len(tables) <= 8:
        return False
    plus = any("хондрофит плюс" in label_match_norm(row.get("source_name") or "") for row in products)

    packaging_table = tables[4]
    packaging_rows = []
    for product in products:
        source_name = product.get("source_name") or ""
        volume = extract_volume(source_name)
        dispenser = uses_dispenser(source_name) or volume == 200
        exemplar = mixed_packaging_exemplar(packaging_table, volume, dispenser)
        if exemplar is None:
            continue
        row = copy.deepcopy(exemplar)
        cells = cells_of(row)
        set_text(cells[1], product_display_name(source_name))
        set_text(cells[2], f"{volume} мл")
        if animal_of(source_name) == "horse" and not plus:
            set_text(cells[3], "Выше риски")
        set_text(cells[4], "")
        set_text(cells[5], "")
        if len(cells) > 6:
            set_text(cells[6], "")
        packaging_rows.append(row)
    replace_table_data_rows(packaging_table, packaging_rows)

    marking_table = tables[7]
    marking_rows = []
    label_names = []
    for label in labels:
        source_name = label.get("source_name") or ""
        volume = extract_volume(source_name)
        dispenser = uses_dispenser(source_name) or volume == 200
        exemplar = mixed_label_exemplar(marking_table, volume, dispenser)
        if exemplar is None:
            continue
        row = copy.deepcopy(exemplar)
        cells = cells_of(row)
        display_name = label_display_name(source_name)
        set_text(cells[1], display_name)
        set_text(cells[2], "")
        set_text(cells[3], "")
        marking_rows.append(row)
        label_names.append(display_name)
    replace_table_data_rows(marking_table, marking_rows)

    replace_table_data_rows(tables[6], mixed_tare_rows(tables[6], products, packaging_rows, plus))

    label_remainder_rows = []
    remainder_source_rows = tables[8].findall("./w:tr", NS)[1:]
    if remainder_source_rows:
        for label_name in label_names:
            row = copy.deepcopy(remainder_source_rows[0])
            cells = cells_of(row)
            set_text(cells[0], label_name)
            if len(cells) > 1:
                set_text(cells[1], "")
            label_remainder_rows.append(row)
    replace_table_data_rows(tables[8], label_remainder_rows)

    combined_name = "Хондропротектор Хондрофит ПЛЮС ArtroPro для собак и лошадей" if plus else "Хондропротектор Хондрофит ArtroPro для собак и лошадей"
    for row in tables[5].findall("./w:tr", NS)[1:]:
        cells = cells_of(row)
        if len(cells) > 1:
            set_text(cells[1], combined_name)
    rewrite_combined_hondrofit_title(document, direct_body_only=True)
    return True
