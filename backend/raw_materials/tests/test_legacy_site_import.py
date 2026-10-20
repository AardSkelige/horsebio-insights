import sqlite3
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.test import TestCase

from raw_materials.models import Batch, BatchMovement, MaterialStock, Slot
from raw_materials.services.legacy_site_import import ImportBlocked, convert, import_batches, normalize
from raw_materials.tests.factories import batch, material


def legacy_site_db(path, rows):
    connection = sqlite3.connect(path)
    connection.executescript('''
        CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT, category TEXT, unit TEXT, manufacturer TEXT);
        CREATE TABLE batches (id INTEGER PRIMARY KEY, item_id TEXT, series TEXT, received_qty REAL,
            remaining_qty REAL, unit TEXT, expiry_date TEXT, location TEXT, status TEXT, created_at TEXT);
    ''')
    for index, (name, item_unit, batch_unit, series, quantity, expiry, location, status) in enumerate(rows):
        connection.execute('INSERT INTO items VALUES (?, ?, ?, ?, ?)', (f'i{index}', name, 'raw', item_unit, ' ВИТАСОЛЬ '))
        connection.execute(
            'INSERT INTO batches (item_id, series, received_qty, remaining_qty, unit, expiry_date, location, status, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (f'i{index}', series, quantity, quantity, batch_unit, expiry, location, status, '2026-05-06 14:29:54'),
        )
    connection.commit()
    connection.close()


class NormalizeTests(TestCase):
    def test_latin_letters_and_typos_match_moysklad_names(self):
        self.assertEqual(normalize('Витамин E 98% (жидкий)'), normalize('Витамин Е 98% (жидкий)'))
        self.assertEqual(normalize('Соевый  лицетин'), 'соевый лецитин')

    def test_units_convert_to_moysklad_base(self):
        self.assertEqual(convert(150, 'кг', 'г'), Decimal('150000'))
        self.assertEqual(convert(2, 'л', 'Мл'), Decimal('2000'))
        with self.assertRaises(ValueError):
            convert(1, 'кг', 'шт')


class ImportTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'warehouse.db')
        self.addCleanup(self.tmp.cleanup)

    def test_batches_land_on_moysklad_materials(self):
        multicalcium = material('Витаминная смесь (Мультикальций)')
        lids = material('Крышка двухкомпонентная (горло 48мм)', uom='шт')
        Slot.objects.create(external_id='s-c4', name='C4')
        legacy_site_db(self.path, [
            ('Витаминная смесь (Мультикальций)', 'кг', 'кг', '379', 150, '2026-11-11', 'B2', 'active'),
            ('Витаминная смесь (Мультикальций)', 'кг', 'г', '119', 25000, '', 'B2', 'active'),
            ('Крышка двухкомпонентная (горло 48мм)', 'шт', 'шт', 'Б/С', 4200, None, 'с4 стеллаж', 'active'),
            ('Экстракт Алое', 'г', 'г', '1', 10, None, 'B5', 'active'),
            ('Ведро', 'шт', 'шт', '1', 10, None, 'B5', 'closed'),
        ])

        report = import_batches(self.path)

        self.assertEqual(report['imported'], 3)
        self.assertEqual(report['unmatched'], ['Экстракт Алое'])
        series = {b.series: b for b in Batch.objects.filter(material=multicalcium)}
        self.assertEqual(series['379'].quantity, Decimal('150000'))
        self.assertEqual(series['379'].expiry_date, date(2026, 11, 11))
        self.assertEqual(series['379'].manufacturer, 'ВИТАСОЛЬ')
        self.assertIsNone(series['119'].expiry_date)
        self.assertEqual(Batch.objects.get(material=lids).series, '')
        self.assertEqual(MaterialStock.objects.get(material=lids).slot.name, 'C4')
        self.assertEqual(BatchMovement.objects.filter(kind=BatchMovement.IMPORT).count(), 3)

    def test_rerun_replaces_previous_import(self):
        material('Биотин')
        legacy_site_db(self.path, [('Биотин', 'г', 'г', 'A', 4000, None, 'B5', 'active')])
        import_batches(self.path)
        import_batches(self.path)
        self.assertEqual(Batch.objects.count(), 1)

    def test_working_movements_block_the_import(self):
        biotin = material('Биотин')
        BatchMovement.objects.create(batch=batch(biotin, '5'), kind='issue', quantity=Decimal('-5'))
        legacy_site_db(self.path, [])
        with self.assertRaises(ImportBlocked):
            import_batches(self.path)
