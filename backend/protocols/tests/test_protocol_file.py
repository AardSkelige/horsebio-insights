from datetime import date

from django.test import TestCase

from protocols.models import ManualSeries
from protocols.services.protocol_file import ProtocolError, build
from protocols.tests.factories import link, material, plan_row, row_material, task, template, text_of


class BuildTests(TestCase):
    def setUp(self):
        self.calcium = material('Витаминная смесь (Мультикальций)', 'm-mc')
        self.template = template('Мультикальций', rows=['Мультикальций'])
        row_material(self.template, 'Мультикальций', self.calcium)
        link('p-1', self.template)
        self.task = task(plan_row('p-1', [('МультиКальций 1000 г', 10)], [('m-mc', 'Витаминная смесь (Мультикальций)', 9500)]))

    def rows(self, **overrides):
        return [{
            'row_name': 'Мультикальций', 'material_id': 'm-mc', 'qty': 9500,
            'series': '379', 'expiry_date': '2026-11-11', 'manufacturer': 'ВИТАСОЛЬ', **overrides,
        }]

    def test_document_carries_task_number_series_and_dosage(self):
        content, filename = build(self.task, 0, self.rows())
        xml = text_of(content)
        self.assertIn('Серия 00689', xml)
        self.assertIn('ВИТАСОЛЬ партия № 379', xml)
        self.assertIn('11.11.2026', xml)
        self.assertIn('9500 г', xml)
        self.assertEqual(filename, 'Протокол 00689 Мультикальций.docx')

    def test_quantity_carries_the_moysklad_unit_instead_of_grams_in_the_header(self):
        oil = material('Масло льняное', 'm-oil', uom='Мл')
        echinacea = template('Эхинацея', rows=['Льняное масло'])
        row_material(echinacea, 'Льняное масло', oil)
        link('p-2', echinacea)
        oil_task = task(plan_row('p-2', [('Эхинацея 1000 мл', 20)], [('m-oil', 'Масло льняное', 19200)]))
        xml = text_of(build(oil_task, 0, [{'row_name': 'Льняное масло', 'material_id': 'm-oil', 'qty': 19200}])[0])
        self.assertIn('19200 мл', xml)
        self.assertIn('Дозировка теоретическое кол-во<', xml)
        self.assertNotIn('грамм', xml)

    def test_series_typed_by_hand_is_remembered(self):
        build(self.task, 0, self.rows(series='A-77', expiry_date='2027-05-01'))
        manual = ManualSeries.objects.get(material=self.calcium)
        self.assertEqual((manual.series, manual.expiry_date), ('A-77', date(2027, 5, 1)))

    def test_without_template_there_is_no_protocol(self):
        with self.assertRaises(ProtocolError):
            build(task(plan_row('p-unknown', [], [])), 0, [])
