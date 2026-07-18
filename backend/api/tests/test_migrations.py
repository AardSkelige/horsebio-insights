from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase


class UserHomePreferenceMigrationTests(TransactionTestCase):
    migrate_from = ('api', '0007_seed_health_check_exceptions')
    migrate_to = ('api', '0008_userhomepreference')

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])

        target_apps = executor.loader.project_state([self.migrate_to]).apps
        UserHomePreference = target_apps.get_model('api', 'UserHomePreference')

        # Reproduce the production state left by the competing migration run:
        # the table exists, while api.0008 is not recorded as applied.
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(UserHomePreference)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def test_existing_table_is_adopted_without_recreating_it(self):
        UserHomePreference = self.apps.get_model('api', 'UserHomePreference')
        table_name = UserHomePreference._meta.db_table

        self.assertIn(table_name, connection.introspection.table_names())
        self.assertTrue(
            MigrationRecorder(connection).migration_qs.filter(
                app='api',
                name='0008_userhomepreference',
            ).exists()
        )
