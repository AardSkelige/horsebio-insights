import re
import xml.etree.ElementTree as ET
import zipfile

from .wordml import NS, cells_of, enable_field_updates, format_row_cells, rows_of, set_text, text_of
from .matching import best_label_for_row, docx_qty_text, extract_package_count, extract_volume, label_display_name, label_match_norm, metadata_value, pack_amount, producer_series_text, product_display_name
from .layout import add_automation_notice, fill_process_defaults, keep_completion_section_together, keep_document_tables_together, keep_process_heading_with_content, normalize_header_page_fields, normalize_protocol_spacing, remove_empty_output_spacers, replace_series_suffix, widen_material_expiry_column
from .tables import prune_related_label_rows, prune_unused_quantity_rows, quantity_table, set_sealing_datetime_row, task_requires_sealing
from .hondrofit import hondrofit_water_dosages, prepare_mixed_hondrofit, rewrite_combined_hondrofit_title

GRAMS_IN_HEADER = re.compile(r",\s*грамм.*$", re.S)
BARE_NUMBER = re.compile(r"\s*\d[\d\s.,]*")
WATER_UNIT = "г"


def with_unit(qty_text, unit):
    return f"{qty_text} {unit}" if qty_text and unit else qty_text

def template_material_names(template_path):
    with zipfile.ZipFile(template_path, "r") as zin:
        document = ET.fromstring(zin.read("word/document.xml"))
    out = []
    for row in rows_of(document, 2)[1:]:
        cells = cells_of(row)
        if not cells:
            continue
        name = text_of(cells[0]).strip()
        if name and "вода" not in name.lower() and "РІРѕРґР°" not in name.lower():
            out.append(name)
    return out


def build_docx(template_path, output_path, batch_no, resolved_materials, labels, products=None):
    products = products or []
    with zipfile.ZipFile(template_path, "r") as zin:
        files = {name: zin.read(name) for name in zin.namelist()}

    document = ET.fromstring(files["word/document.xml"])
    replace_series_suffix(document, batch_no)
    mixed_hondrofit = prepare_mixed_hondrofit(document, products, labels)
    widen_material_expiry_column(document)
    keep_process_heading_with_content(document)
    add_automation_notice(document)
    fill_process_defaults(document)

    headers = {}
    for name in files:
        if re.fullmatch(r"word/header\d+\.xml", name):
            header = ET.fromstring(files[name])
            replace_series_suffix(header, batch_no)
            normalize_header_page_fields(header)
            if mixed_hondrofit:
                rewrite_combined_hondrofit_title(header)
            headers[name] = header

    material_by_name = {row["template_name"]: row for row in resolved_materials if row.get("template_name")}
    material_rows = rows_of(document, 2)
    water_dosages = hondrofit_water_dosages(template_path)
    water_index = 0
    for idx, row in enumerate(material_rows):
        cells = cells_of(row)
        if len(cells) < 5:
            continue
        format_row_cells(cells[:5])
        if idx == 0:
            for cell in cells[3:5]:
                set_text(cell, GRAMS_IN_HEADER.sub("", text_of(cell)))
            continue
        name = text_of(cells[0]).strip()
        is_water = "вода" in name.lower() or "РІРѕРґР°" in name
        is_sodium_benzoate = "бензоат натрия" in label_match_norm(name)
        is_selenium = "селен" in set(label_match_norm(name).split())
        set_text(cells[1], "")
        set_text(cells[2], "")
        if not is_water:
            set_text(cells[3], "")
        elif water_index < len(water_dosages):
            set_text(cells[1], "—")
            set_text(cells[2], "—")
            set_text(cells[3], with_unit(docx_qty_text(water_dosages[water_index]), WATER_UNIT))
            water_index += 1
            continue
        if is_water and BARE_NUMBER.fullmatch(text_of(cells[3])):
            set_text(cells[3], with_unit(text_of(cells[3]).strip(), WATER_UNIT))
        data = material_by_name.get(name)
        if not data:
            set_text(cells[1], "—")
            set_text(cells[2], "—")
            continue
        set_text(cells[1], producer_series_text(data.get("manufacturer"), data.get("series")))
        expiry_date = metadata_value(data.get("expiry_date"))
        set_text(cells[2], "—" if is_sodium_benzoate or not expiry_date else expiry_date)
        if not is_selenium:
            set_text(cells[3], with_unit(docx_qty_text(data.get("qty")), (data.get("uom") or "").lower()))

    primary_label_table = None
    primary_label_match_complete = False
    matched_product_rows = []
    for quantity_kind, table_info, quantity_rows in (
        ("products", quantity_table(document, "products"), products),
        ("labels", quantity_table(document, "labels"), labels),
    ):
        if not table_info:
            continue
        table, volume_cell_index, qty_cell_index = table_info
        if quantity_kind == "labels":
            primary_label_table = table
        used_labels = set()
        candidate_rows = []
        matched_rows = []
        table_rows = table.findall("./w:tr", NS)
        for idx, row in enumerate(table_rows):
            cells = cells_of(row)
            required_indexes = [qty_cell_index]
            if volume_cell_index is not None:
                required_indexes.append(volume_cell_index)
            if len(cells) <= max(required_indexes):
                continue
            format_row_cells(cells)
            if idx == 0:
                continue
            candidate_rows.append(row)
            set_text(cells[qty_cell_index], "")
            row_text = " ".join(text_of(cell) for cell in cells)
            target_volume = (
                (
                    extract_volume(text_of(cells[volume_cell_index]))
                    or extract_package_count(text_of(cells[volume_cell_index]))
                    or pack_amount(text_of(cells[volume_cell_index]))
                )
                if volume_cell_index is not None
                else None
            )
            label_index = best_label_for_row(
                row_text,
                quantity_rows,
                used_labels,
                target_volume,
                target_measure_supplied=volume_cell_index is not None,
            )
            if label_index is not None:
                quantity_data = quantity_rows[label_index]
                used_labels.add(label_index)
                matched_rows.append(row)
                packaging_name = str(quantity_data.get("packaging_name") or "").strip()
                if packaging_name:
                    set_text(cells[0], packaging_name)
                    source_name = quantity_data.get("source_name") or ""
                    if quantity_kind == "products" and len(cells) > 1:
                        set_text(cells[1], product_display_name(source_name))
                    elif quantity_kind == "labels" and volume_cell_index is not None:
                        set_text(cells[volume_cell_index], label_display_name(source_name))
                set_text(cells[qty_cell_index], docx_qty_text(quantity_data.get("qty")))
        table_pruned = prune_unused_quantity_rows(
            table,
            candidate_rows,
            matched_rows,
            len(quantity_rows),
            len(used_labels),
        )
        if quantity_kind == "products":
            matched_product_rows = list(matched_rows)
        if quantity_kind == "labels":
            primary_label_match_complete = table_pruned

    prune_related_label_rows(
        document,
        labels,
        primary_label_table,
        match_complete=primary_label_match_complete,
    )
    set_sealing_datetime_row(
        document,
        task_requires_sealing(products, matched_product_rows),
    )
    remove_empty_output_spacers(document)
    keep_completion_section_together(document)

    normalize_protocol_spacing(document)
    keep_document_tables_together(document)

    files["word/document.xml"] = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    for name, header in headers.items():
        files[name] = ET.tostring(header, encoding="utf-8", xml_declaration=True)
    if "word/settings.xml" in files:
        settings = ET.fromstring(files["word/settings.xml"])
        enable_field_updates(settings)
        files["word/settings.xml"] = ET.tostring(settings, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in files.items():
            zout.writestr(name, data)
