import copy
import xml.etree.ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
VYD_NS = "http://volga.yandex.com/schemas/document/model"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS = {"w": W_NS}
ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("w14", W14_NS)
ET.register_namespace("vyd", VYD_NS)
ET.register_namespace("mc", MC_NS)

def wtag(tag):
    return f"{{{W_NS}}}{tag}"


def text_of(node):
    return "".join(t.text or "" for t in node.findall(".//w:t", NS))


def set_text(node, value):
    runs = node.findall(".//w:t", NS)
    if runs:
        runs[0].text = str(value)
        for extra in runs[1:]:
            extra.text = ""
        return
    p = node.find(".//w:p", NS)
    if p is None:
        p = ET.SubElement(node, wtag("p"))
    r = ET.SubElement(p, wtag("r"))
    t = ET.SubElement(r, wtag("t"))
    t.text = str(value)


def ensure_child(node, tag):
    child = node.find(f"./w:{tag}", NS)
    if child is None:
        child = ET.Element(wtag(tag))
        if tag in {"tcPr", "pPr", "rPr"}:
            node.insert(0, child)
        else:
            node.append(child)
    return child


def enable_pagination_flag(properties, tag):
    flag = properties.find(f"./w:{tag}", NS)
    if flag is None:
        flag = ET.SubElement(properties, wtag(tag))
    flag.set(wtag("val"), "1")


def cells_of(row):
    return row.findall("./w:tc", NS)


def rows_of(root, table_index):
    tables = root.findall(".//w:tbl", NS)
    return tables[table_index].findall("./w:tr", NS)


def field_names(node):
    return [" ".join((item.text or "").split()).upper() for item in node.findall(".//w:instrText", NS)]


def append_text_run(paragraph, value, r_pr=None):
    run = ET.SubElement(paragraph, wtag("r"))
    if r_pr is not None:
        run.append(copy.deepcopy(r_pr))
    text = ET.SubElement(run, wtag("t"))
    if value.startswith(" ") or value.endswith(" "):
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = value


def append_field(paragraph, instruction, cached, r_pr=None):
    begin = ET.SubElement(paragraph, wtag("r"))
    if r_pr is not None:
        begin.append(copy.deepcopy(r_pr))
    begin_char = ET.SubElement(begin, wtag("fldChar"))
    begin_char.set(wtag("fldCharType"), "begin")
    begin_char.set(wtag("dirty"), "true")

    code = ET.SubElement(paragraph, wtag("r"))
    if r_pr is not None:
        code.append(copy.deepcopy(r_pr))
    instruction_text = ET.SubElement(code, wtag("instrText"))
    instruction_text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instruction_text.text = f" {instruction} "

    separate = ET.SubElement(paragraph, wtag("r"))
    if r_pr is not None:
        separate.append(copy.deepcopy(r_pr))
    separate_char = ET.SubElement(separate, wtag("fldChar"))
    separate_char.set(wtag("fldCharType"), "separate")
    append_text_run(paragraph, cached, r_pr)

    end = ET.SubElement(paragraph, wtag("r"))
    if r_pr is not None:
        end.append(copy.deepcopy(r_pr))
    end_char = ET.SubElement(end, wtag("fldChar"))
    end_char.set(wtag("fldCharType"), "end")


def enable_field_updates(settings):
    update = settings.find("./w:updateFields", NS)
    if update is None:
        update = ET.SubElement(settings, wtag("updateFields"))
    update.set(wtag("val"), "true")


def format_cell(cell, font="Times New Roman", size_half_points="24", align="center"):
    tc_pr = ensure_child(cell, "tcPr")
    v_align = tc_pr.find("./w:vAlign", NS)
    if v_align is None:
        v_align = ET.SubElement(tc_pr, wtag("vAlign"))
    v_align.set(wtag("val"), "center")

    for p in cell.findall(".//w:p", NS):
        p_pr = ensure_child(p, "pPr")
        jc = p_pr.find("./w:jc", NS)
        if jc is None:
            jc = ET.SubElement(p_pr, wtag("jc"))
        jc.set(wtag("val"), align)

        for r in p.findall(".//w:r", NS):
            r_pr = ensure_child(r, "rPr")
            r_fonts = r_pr.find("./w:rFonts", NS)
            if r_fonts is None:
                r_fonts = ET.SubElement(r_pr, wtag("rFonts"))
            r_fonts.set(wtag("ascii"), font)
            r_fonts.set(wtag("hAnsi"), font)
            r_fonts.set(wtag("cs"), font)
            sz = r_pr.find("./w:sz", NS)
            if sz is None:
                sz = ET.SubElement(r_pr, wtag("sz"))
            sz.set(wtag("val"), size_half_points)
            sz_cs = r_pr.find("./w:szCs", NS)
            if sz_cs is None:
                sz_cs = ET.SubElement(r_pr, wtag("szCs"))
            sz_cs.set(wtag("val"), size_half_points)


def format_row_cells(cells):
    for cell in cells:
        format_cell(cell)
