from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from inventory_tracking.models import CellsUploadLog, InventoryRun, ProductInventoryStatus
from inventory_tracking.services.inventory_checker import InventoryChecker


class SavedCellsUploadsTests(TestCase):
    month_start = date(2026, 7, 1)

    def setUp(self):
        self.previous_run = InventoryRun.objects.create(
            month_start=self.month_start,
            total_products=1,
            inventoried_count=1,
            not_inventoried_count=0,
        )
        ProductInventoryStatus.objects.create(
            run=self.previous_run,
            external_id='product-1',
            code='CODE-1',
            name='Product 1',
            folder='Товары',
            is_inventoried=True,
            inventory_count=1,
        )
        self.upload = CellsUploadLog.objects.create(
            run=self.previous_run,
            month_start=self.month_start,
            inventory_name='00022',
            inventory_date=date(2026, 7, 10),
            warehouse='Склад',
            codes=['CODE-1'],
            matched_count=1,
        )

    def test_saved_upload_is_applied_to_new_run_for_same_month(self):
        new_run = InventoryChecker()._save_run(
            products=[{
                'id': 'product-1',
                'code': 'CODE-1',
                'name': 'Product 1',
                '_category': 'Товары',
            }],
            seen_map={},
            month_start=self.month_start,
            triggered_by='manual',
            is_month_snapshot=False,
        )

        status = new_run.products.get(external_id='product-1')
        self.assertTrue(status.is_inventoried)
        self.assertEqual(status.inventory_count, 1)
        self.assertEqual(timezone.localdate(status.last_inventoried_at), date(2026, 7, 10))
        new_run.refresh_from_db()
        self.assertEqual(new_run.inventoried_count, 1)
        self.assertEqual(new_run.not_inventoried_count, 0)
        self.upload.refresh_from_db()
        self.assertEqual(self.upload.run, new_run)

    def test_upload_survives_deletion_of_the_snapshot(self):
        self.previous_run.delete()

        self.upload.refresh_from_db()
        self.assertIsNone(self.upload.run)
        self.assertEqual(self.upload.month_start, self.month_start)
        self.assertEqual(self.upload.codes, ['CODE-1'])

    def test_upload_from_another_month_is_not_applied(self):
        new_run = InventoryChecker()._save_run(
            products=[{
                'id': 'product-1',
                'code': 'CODE-1',
                'name': 'Product 1',
                '_category': 'Товары',
            }],
            seen_map={},
            month_start=date(2026, 8, 1),
            triggered_by='manual',
            is_month_snapshot=False,
        )

        status = new_run.products.get(external_id='product-1')
        self.assertFalse(status.is_inventoried)
        self.assertEqual(new_run.inventoried_count, 0)


class CellsUploadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='secret')
        self.client.login(username='tester', password='secret')
        self.run = InventoryRun.objects.create(month_start=date(2026, 7, 1))

    @patch('inventory_tracking.services.xls_cells_parser.apply_cells_upload', return_value=1)
    @patch('inventory_tracking.services.xls_cells_parser.parse_cells_inventory_xls')
    def test_upload_persists_codes_for_future_runs(self, parse_xls, _apply_upload):
        parse_xls.return_value = {
            'inventory_name': '00022',
            'inventory_date': date(2026, 7, 10),
            'warehouse': 'Склад',
            'codes': ['CODE-1'],
        }

        response = self.client.post(
            '/api/inventory/upload-cells/',
            {
                'month': '2026-07',
                'file': SimpleUploadedFile('inventory.xls', b'xls'),
            },
        )

        self.assertEqual(response.status_code, 200)
        upload = CellsUploadLog.objects.get(inventory_name='00022')
        self.assertEqual(upload.month_start, date(2026, 7, 1))
        self.assertEqual(upload.codes, ['CODE-1'])
