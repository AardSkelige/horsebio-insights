from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PersistCellsUploadContentsMigrationTests(TransactionTestCase):
    migrate_from = ('inventory_tracking', '0003_cellsuploadlog')
    migrate_to = ('inventory_tracking', '0004_persist_cells_upload_contents')

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps

        InventoryRun = old_apps.get_model('inventory_tracking', 'InventoryRun')
        CellsUploadLog = old_apps.get_model('inventory_tracking', 'CellsUploadLog')

        run = InventoryRun.objects.create(month_start=date(2026, 7, 1))
        CellsUploadLog.objects.create(
            run=run,
            inventory_name='00022',
            inventory_date=date(2026, 7, 10),
            matched_count=1,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def test_existing_upload_month_is_backfilled_without_guessing_codes(self):
        CellsUploadLog = self.apps.get_model(
            'inventory_tracking',
            'CellsUploadLog',
        )

        upload = CellsUploadLog.objects.get(inventory_name='00022')
        self.assertEqual(upload.month_start, date(2026, 7, 1))
        self.assertEqual(upload.codes, [])
