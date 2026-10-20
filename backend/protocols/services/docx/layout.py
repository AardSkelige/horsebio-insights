import copy
import re
import xml.etree.ElementTree as ET

from .wordml import NS, append_field, append_text_run, cells_of, enable_pagination_flag, ensure_child, field_names, set_text, text_of, wtag
from .matching import label_match_norm

AUTOMATION_NOTICE = "Протокол сформирован с использованием автоматизированной системы подготовки технологических протоколов."


def keep_table_together(table):
    rows = table.findall("./w:tr", NS)
    for row_index, row in enumerate(rows):
        tr_pr = ensure_child(row, "trPr")
        enable_pagination_flag(tr_pr, "cantSplit")
        for paragraph in row.findall(".//w:p", NS):
            p_pr = ensure_child(paragraph, "pPr")
            enable_pagination_flag(p_pr, "keepLines")
            if row_index < len(rows) - 1:
                enable_pagination_flag(p_pr, "keepNext")


def keep_document_tables_together(document):
    for table in document.findall(".//w:tbl", NS):
        keep_table_together(table)

    body = document.find("./w:body", NS)
    if body is None:
        return
    children = list(body)
    for index, child in enumerate(children):
        if child.tag != wtag("tbl"):
            continue
        previous_index = index - 1
        while previous_index >= 0 and children[previous_index].tag == wtag("p"):
            paragraph = children[previous_index]
            p_pr = ensure_child(paragraph, "pPr")
            enable_pagination_flag(p_pr, "keepNext")
            if text_of(paragraph).strip():
                break
            previous_index -= 1


def normalize_protocol_spacing(document):
    table_paragraphs = {
        id(paragraph)
        for table in document.findall(".//w:tbl", NS)
        for paragraph in table.findall(".//w:p", NS)
    }
    for paragraph in document.findall(".//w:p", NS):
        p_pr = ensure_child(paragraph, "pPr")
        spacing = p_pr.find("./w:spacing", NS)
        if spacing is None:
            spacing = ET.SubElement(p_pr, wtag("spacing"))

        if id(paragraph) in table_paragraphs:
            spacing.set(wtag("before"), "0")
            spacing.set(wtag("after"), "0")
            spacing.set(wtag("line"), "240")
            spacing.set(wtag("lineRule"), "auto")
            continue

        for attribute in ("before", "after"):
            raw_value = spacing.get(wtag(attribute))
            if raw_value and raw_value.isdigit() and int(raw_value) > 120:
                spacing.set(wtag(attribute), "120")


def replace_series_suffix(root, batch_no):
    replacement = f"Серия {batch_no}"
    patterns = (
        re.compile(r"Серия(?:[\s_\xa0])*$", re.I),
        re.compile(r"РЎРµСЂРёСЏ(?:[\s_\xa0])*$", re.I),
    )
    for paragraph in root.findall(".//w:p", NS):
        text_nodes = paragraph.findall(".//w:t", NS)
        if not text_nodes:
            continue
        full_text = "".join(node.text or "" for node in text_nodes)
        match = next((pattern.search(full_text) for pattern in patterns if pattern.search(full_text)), None)
        if not match:
            continue
        offset = 0
        for index, node in enumerate(text_nodes):
            node_text = node.text or ""
            node_end = offset + len(node_text)
            if match.start() <= node_end:
                local_start = max(0, match.start() - offset)
                node.text = node_text[:local_start] + replacement
                for extra in text_nodes[index + 1:]:
                    extra.text = ""
                break
            offset = node_end


def normalize_header_page_fields(header):
    for paragraph in header.findall(".//w:p", NS):
        fields = field_names(paragraph)
        visible = text_of(paragraph).lower()
        if "страниц" not in visible and "PAGE" not in fields:
            continue
        if fields == ["PAGE", "NUMPAGES"]:
            return False
        source_r_pr = paragraph.find(".//w:r/w:rPr", NS)
        source_r_pr = copy.deepcopy(source_r_pr) if source_r_pr is not None else None
        for child in list(paragraph):
            if child.tag != wtag("pPr"):
                paragraph.remove(child)
        append_text_run(paragraph, "Страница ", source_r_pr)
        append_field(paragraph, "PAGE", "1", source_r_pr)
        append_text_run(paragraph, " из ", source_r_pr)
        append_field(paragraph, "NUMPAGES", "1", source_r_pr)
        return True
    return False


def keep_process_heading_with_content(document):
    body = document.find("./w:body", NS)
    if body is None:
        return
    children = list(body)
    for index, child in enumerate(children):
        if child.tag != wtag("p"):
            continue
        text = " ".join(text_of(child).lower().replace("ё", "е").split())
        if "производственный процесс" not in text:
            continue

        for following in children[index:]:
            if following.tag == wtag("tbl"):
                break
            if following.tag != wtag("p"):
                continue
            p_pr = ensure_child(following, "pPr")
            enable_pagination_flag(p_pr, "keepNext")
        break


def remove_empty_output_spacers(document):
    body = document.find("./w:body", NS)
    if body is None:
        return 0
    active = False
    removed = 0
    protected_tags = ("drawing", "br", "fldChar", "instrText", "object", "pict")
    for child in list(body):
        if child.tag != wtag("p"):
            continue
        text = label_match_norm(text_of(child))
        if "фасовка готовой продукции" in text:
            active = True
            continue
        if "завершение работ" in text:
            break
        if not active or text:
            continue
        if child.find(".//w:bookmarkStart", NS) is not None or child.find(".//w:bookmarkEnd", NS) is not None:
            continue
        if any(child.find(f".//w:{tag}", NS) is not None for tag in protected_tags):
            continue
        body.remove(child)
        removed += 1
    return removed


def keep_completion_section_together(document):
    body = document.find("./w:body", NS)
    if body is None:
        return
    children = [child for child in list(body) if child.tag != wtag("sectPr")]
    start_index = None
    for index, child in enumerate(children):
        if child.tag != wtag("p"):
            continue
        text = label_match_norm(text_of(child))
        if "завершение работ" in text:
            start_index = index
            break
    if start_index is None:
        return

    protected_tags = ("drawing", "br", "fldChar", "instrText", "object", "pict")
    for child in list(children[start_index + 1:]):
        if child.tag != wtag("p") or text_of(child).strip():
            continue
        if any(child.find(f".//w:{tag}", NS) is not None for tag in protected_tags):
            continue
        if child.find(".//w:bookmarkStart", NS) is not None or child.find(".//w:bookmarkEnd", NS) is not None:
            for run in list(child.findall("./w:r", NS)):
                child.remove(run)
            p_pr = ensure_child(child, "pPr")
            spacing = ensure_child(p_pr, "spacing")
            spacing.set(wtag("before"), "0")
            spacing.set(wtag("after"), "0")
            spacing.set(wtag("line"), "20")
            spacing.set(wtag("lineRule"), "exact")
            continue
        body.remove(child)

    children = [child for child in list(body) if child.tag != wtag("sectPr")]
    start_index = next(
        index for index, child in enumerate(children)
        if child.tag == wtag("p") and "завершение работ" in label_match_norm(text_of(child))
    )
    section_children = children[start_index:]
    for child_index, child in enumerate(section_children):
        paragraphs = [child] if child.tag == wtag("p") else child.findall(".//w:p", NS)
        for paragraph in paragraphs:
            p_pr = ensure_child(paragraph, "pPr")
            enable_pagination_flag(p_pr, "keepLines")
            if child_index < len(section_children) - 1:
                enable_pagination_flag(p_pr, "keepNext")


def add_automation_notice(document):
    body = document.find("./w:body", NS)
    if body is None:
        return False
    if "автоматизированной системы подготовки технологических протоколов" in label_match_norm(text_of(body)):
        return True

    verification_paragraph = None
    for child in list(body):
        if child.tag != wtag("p"):
            continue
        if "технологический протокол проверен" in label_match_norm(text_of(child)):
            verification_paragraph = child
            break
    if verification_paragraph is None:
        return False

    paragraph = ET.Element(wtag("p"))
    p_pr = ET.SubElement(paragraph, wtag("pPr"))
    spacing = ET.SubElement(p_pr, wtag("spacing"))
    spacing.set(wtag("before"), "0")
    spacing.set(wtag("after"), "60")
    spacing.set(wtag("line"), "180")
    spacing.set(wtag("lineRule"), "auto")
    enable_pagination_flag(p_pr, "keepNext")

    run = ET.SubElement(paragraph, wtag("r"))
    r_pr = ET.SubElement(run, wtag("rPr"))
    fonts = ET.SubElement(r_pr, wtag("rFonts"))
    fonts.set(wtag("ascii"), "Times New Roman")
    fonts.set(wtag("hAnsi"), "Times New Roman")
    fonts.set(wtag("cs"), "Times New Roman")
    italic = ET.SubElement(r_pr, wtag("i"))
    italic.set(wtag("val"), "1")
    size = ET.SubElement(r_pr, wtag("sz"))
    size.set(wtag("val"), "16")
    size_cs = ET.SubElement(r_pr, wtag("szCs"))
    size_cs.set(wtag("val"), "16")
    text = ET.SubElement(run, wtag("t"))
    text.text = AUTOMATION_NOTICE

    body.insert(list(body).index(verification_paragraph), paragraph)
    return True


def add_missing_material_expiry_column(table, target_width=1550):
    rows = table.findall("./w:tr", NS)
    grid_columns = table.findall("./w:tblGrid/w:gridCol", NS)
    if not rows or len(grid_columns) != 4:
        return False
    header_cells = cells_of(rows[0])
    headers = [label_match_norm(text_of(cell)) for cell in header_cells]
    if len(header_cells) != 4 or any("годен" in header for header in headers):
        return False

    try:
        widths = [float(column.get(wtag("w")) or 0) for column in grid_columns]
    except ValueError:
        return False
    remaining = widths[2] + widths[3] - target_width
    if remaining < 2800:
        return False
    new_widths = [widths[0], widths[1], target_width, remaining / 2, remaining / 2]

    grid_parent = table.find("./w:tblGrid", NS)
    new_grid = ET.Element(wtag("gridCol"))
    grid_parent.insert(2, new_grid)
    for column_index, width in enumerate(new_widths):
        table.findall("./w:tblGrid/w:gridCol", NS)[column_index].set(wtag("w"), str(int(round(width))))

    for row_index, row in enumerate(rows):
        row_cells = cells_of(row)
        donor = row_cells[2] if row_index == 0 else row_cells[1]
        new_cell = copy.deepcopy(donor)
        set_text(new_cell, "Годен до" if row_index == 0 else "")
        row.insert(2, new_cell)
    return True


def widen_material_expiry_column(document, target_width=1550):
    tables = document.findall(".//w:tbl", NS)
    if len(tables) <= 2:
        return
    table = tables[2]
    add_missing_material_expiry_column(table, target_width)
    grid_columns = table.findall("./w:tblGrid/w:gridCol", NS)
    if len(grid_columns) < 5:
        return

    try:
        producer_width = float(grid_columns[1].get(wtag("w")) or 0)
        expiry_width = float(grid_columns[2].get(wtag("w")) or 0)
    except ValueError:
        return
    if producer_width <= 0:
        return

    try:
        widths = [float(column.get(wtag("w")) or 0) for column in grid_columns]
    except ValueError:
        return
    delta = target_width - expiry_width
    if delta > 0:
        for column_index, minimum_width in ((1, 1800), (4, 1400), (3, 1400), (0, 1600)):
            if column_index >= len(widths):
                continue
            available = max(0, widths[column_index] - minimum_width)
            shift = min(delta, available)
            widths[column_index] -= shift
            delta -= shift
            if delta <= 0:
                break
        if delta > 0:
            return
    elif delta < 0:
        widths[1] += -delta
    widths[2] = target_width
    producer_width = widths[1]
    expiry_width = widths[2]

    def width_text(value):
        return str(int(round(value)))

    for column_index, width in enumerate(widths):
        if column_index < len(grid_columns):
            grid_columns[column_index].set(wtag("w"), width_text(width))

    for row in table.findall("./w:tr", NS):
        cells = cells_of(row)
        if len(cells) != 5:
            continue
        for column_index, width in enumerate(widths[:5]):
            tc_pr = ensure_child(cells[column_index], "tcPr")
            tc_width = ensure_child(tc_pr, "tcW")
            tc_width.set(wtag("w"), width_text(width))
            tc_width.set(wtag("type"), "dxa")
        expiry_pr = ensure_child(cells[2], "tcPr")
        no_wrap = ensure_child(expiry_pr, "noWrap")
        no_wrap.set(wtag("val"), "1")


def fill_process_defaults(document):
    for table in document.findall(".//w:tbl", NS):
        rows = table.findall("./w:tr", NS)
        if not rows:
            continue
        header_cells = cells_of(rows[0])
        headers = [label_match_norm(text_of(cell)) for cell in header_cells]
        header_text = " ".join(headers)
        if not (
            len(headers) >= 4
            and "операц" in header_text
            and "параметр" in header_text
            and "регламент" in header_text
            and "фактическ" in header_text
        ):
            continue

        for row in rows[1:]:
            cells = cells_of(row)
            if len(cells) < 4:
                continue
            operation = label_match_norm(text_of(cells[0]))
            if "добав" in operation and "продукт" in operation and "сер" in operation:
                set_text(cells[2], "—")
                continue
            if "фасовка готовой продукции" in operation and "использованием пакета" in operation:
                set_text(cells[1], "X")
                set_text(cells[2], "да")
                set_text(cells[3], "да □ нет □")
