import tempfile
from pathlib import Path

from protocols.services.docx.build import build_docx, template_material_names


def _template_file(template, folder):
    path = Path(folder) / Path(template.file_name).name
    path.write_bytes(bytes(template.content))
    return path


def template_rows(template):
    with tempfile.TemporaryDirectory() as folder:
        return template_material_names(_template_file(template, folder))


def render(template, batch_no, materials, labels, products):
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder) / 'protocol.docx'
        build_docx(_template_file(template, folder), output, batch_no, materials, labels, products)
        return output.read_bytes()
