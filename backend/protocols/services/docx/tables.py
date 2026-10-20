import copy

from .wordml import NS, cells_of, set_text, text_of, wtag
from .matching import extract_volume, label_match_norm, row_match_tokens

def quantity_table(root, kind):
    for table in root.findall(".//w:tbl", NS):
        rows = table.findall("./w:tr", NS)
        if not rows:
            continue
        header_cells = cells_of(rows[0])
        headers = [label_match_norm(text_of(cell)) for cell in header_cells]
        has_theoretical = any("теорет" in header for header in headers)
        if not has_theoretical:
            continue
        qty_index = next((idx for idx, header in enumerate(headers) if "теорет" in header), None)
        if qty_index is None:
            continue
        if kind == "labels":
            volume_index = next((idx for idx, header in enumerate(headers) if "этикет" in header), None)
            if volume_index is not None:
                return table, volume_index, qty_index
            continue
        has_tare = any("наименование тары" in header for header in headers)
        has_label = any("этикет" in header for header in headers)
        if not has_tare or has_label:
            continue
        volume_index = next((idx for idx, header in enumerate(headers) if "фасов" in header), None)
        return table, volume_index, qty_index
    return None


def replace_table_data_rows(table, rows):
    existing = table.findall("./w:tr", NS)
    for row in existing[1:]:
        table.remove(row)
    for row in rows:
        table.append(row)


def prune_unused_quantity_rows(table, candidate_rows, matched_rows, expected_count, matched_count):
    if expected_count <= 0 or matched_count != expected_count:
        return False
    matched_ids = {id(row) for row in matched_rows}
    if len(matched_ids) != expected_count:
        return False
    for row in candidate_rows:
        if id(row) not in matched_ids:
            table.remove(row)
    return True


def prune_related_label_rows(document, labels, primary_table, match_complete=False):
    if not labels or primary_table is None or not match_complete:
        return 0
    body = document.find("./w:body", NS)
    if body is None:
        return 0
    related_tables = []
    previous_heading = ""
    for child in list(body):
        if child.tag == wtag("p"):
            text = label_match_norm(text_of(child))
            if text:
                previous_heading = text
            continue
        if child.tag != wtag("tbl") or child is primary_table:
            continue
        if "брак" in previous_heading and "маркиров" in previous_heading:
            related_tables.append(child)

    selected_names = []
    seen = set()
    for label in labels:
        name = str(label.get("source_name") or "").strip()
        key = label_match_norm(name)
        if name and key not in seen:
            seen.add(key)
            selected_names.append(name)
    if not selected_names:
        return 0

    removed = 0
    for table in related_tables:
        rows = table.findall("./w:tr", NS)
        if len(rows) <= 1:
            continue
        candidates = [row for row in rows[1:] if len(cells_of(row)) >= 2]
        if not candidates:
            continue
        rebuilt = []
        for index, name in enumerate(selected_names):
            exact = next(
                (row for row in candidates if label_match_norm(text_of(cells_of(row)[0])) == label_match_norm(name)),
                None,
            )
            exemplar = exact
            if exemplar is None:
                name_volume = extract_volume(name)
                name_tokens = row_match_tokens(name)
                scored = []
                for row in candidates:
                    row_name = text_of(cells_of(row)[0])
                    row_volume = extract_volume(row_name)
                    if name_volume is not None and row_volume != name_volume:
                        continue
                    score = len(name_tokens & row_match_tokens(row_name))
                    if score:
                        scored.append((score, row))
                scored.sort(key=lambda item: item[0], reverse=True)
                if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                    exemplar = scored[0][1]
            rewrite_name = exemplar is None
            if exemplar is None:
                exemplar = candidates[min(index, len(candidates) - 1)]
            clone = copy.deepcopy(exemplar)
            cells = cells_of(clone)
            if rewrite_name:
                set_text(cells[0], name)
            set_text(cells[1], "")
            rebuilt.append(clone)
        before = len(candidates)
        replace_table_data_rows(table, rebuilt)
        removed += max(0, before - len(rebuilt))
    return removed


def task_requires_sealing(products, matched_product_rows):
    texts = []
    for product in products or []:
        texts.append(product.get("source_name") or "")
        texts.append(product.get("packaging_name") or "")
    for row in matched_product_rows or []:
        cells = cells_of(row)
        if cells:
            texts.append(text_of(cells[0]))

    for text in texts:
        norm = label_match_norm(text)
        tokens = norm.split()
        if "капсул" in norm:
            return True
        if "дой пак" in norm or "дойпак" in norm:
            return True
        if any(token.startswith("банк") for token in tokens):
            return True
    return False


def set_sealing_datetime_row(document, required):
    sealing_norm = "дата время запайки"
    for table in document.findall(".//w:tbl", NS):
        rows = table.findall("./w:tr", NS)
        if len(rows) < 2:
            continue
        header_cells = cells_of(rows[0])
        if len(header_cells) < 2:
            continue
        if label_match_norm(text_of(header_cells[0])) != "наименование":
            continue
        if label_match_norm(text_of(header_cells[1])) != "информация":
            continue

        data_rows = [row for row in rows[1:] if len(cells_of(row)) >= 2]
        if not any("дата время" in label_match_norm(text_of(cells_of(row)[0])) for row in data_rows):
            continue

        sealing_rows = [
            row
            for row in data_rows
            if sealing_norm in label_match_norm(text_of(cells_of(row)[0]))
        ]
        if not required:
            for row in sealing_rows:
                table.remove(row)
            return False

        target = sealing_rows[0] if sealing_rows else None
        for row in sealing_rows:
            table.remove(row)
        base_rows = [row for row in data_rows if row not in sealing_rows]
        anchor = base_rows[min(1, len(base_rows) - 1)]
        if target is None:
            target = copy.deepcopy(anchor)
        insert_at = list(table).index(anchor) + 1
        table.insert(insert_at, target)
        cells = cells_of(target)
        set_text(cells[0], "Дата/время запайки")
        set_text(cells[1], "")
        return True
    return False
