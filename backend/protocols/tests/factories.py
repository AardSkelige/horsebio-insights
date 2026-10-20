import io
import zipfile

from core.models import RawMaterial
from protocols.models import ProtocolTemplate, TemplateLink, TemplateMaterial

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def _cell(text=''):
    return f'<w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>'


def _table(rows):
    return '<w:tbl>' + ''.join('<w:tr>' + ''.join(_cell(c) for c in row) + '</w:tr>' for row in rows) + '</w:tbl>'


def docx(material_rows):
    body = (
        '<w:p><w:r><w:t>Технологический протокол. Серия ____</w:t></w:r></w:p>'
        + _table([['a']]) + _table([['b']])
        + _table([['Сырьё', 'Производитель', 'Годен до', 'Кол-во', 'Подпись']] + [[name, '', '', '', ''] for name in material_rows])
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', xml)
    return buffer.getvalue()


def text_of(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return archive.read('word/document.xml').decode()


def material(name, external_id, group='Материалы для производства', uom='г'):
    return RawMaterial.objects.create(name=name, external_id=external_id, group=group, uom_name=uom)


def template(title, rows=(), merge_into=None):
    return ProtocolTemplate.objects.create(title=title, file_name=f'{title}.docx', content=docx(rows), merge_into=merge_into)


def link(plan_id, template_obj, name=None):
    return TemplateLink.objects.create(plan_external_id=plan_id, plan_name=name or plan_id, template=template_obj)


def row_material(template_obj, row_name, material_obj):
    return TemplateMaterial.objects.create(template=template_obj, row_name=row_name, material=material_obj)


def task(*rows, moment='2026-10-20'):
    return {'id': 't-1', 'name': '00689', 'moment': moment, 'rows': list(rows)}


def plan_row(plan_id, products, materials):
    return {
        'plan_id': plan_id,
        'plan_name': plan_id,
        'products': [{'name': n, 'qty': q} for n, q in products],
        'materials': [{'material_id': mid, 'name': n, 'qty': q} for mid, n, q in materials],
    }
