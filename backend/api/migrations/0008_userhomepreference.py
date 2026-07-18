import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def create_user_home_preference_table(apps, schema_editor):
    """Create the table unless a previous interrupted deploy already did so."""
    model = apps.get_model('api', 'UserHomePreference')
    with schema_editor.connection.cursor() as cursor:
        existing_tables = schema_editor.connection.introspection.table_names(cursor)

    if model._meta.db_table not in existing_tables:
        schema_editor.create_model(model)


def delete_user_home_preference_table(apps, schema_editor):
    model = apps.get_model('api', 'UserHomePreference')
    with schema_editor.connection.cursor() as cursor:
        existing_tables = schema_editor.connection.introspection.table_names(cursor)

    if model._meta.db_table in existing_tables:
        schema_editor.delete_model(model)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_seed_health_check_exceptions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='UserHomePreference',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('pinned_paths', models.JSONField(blank=True, default=list)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('user', models.OneToOneField(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='home_preference',
                            to=settings.AUTH_USER_MODEL,
                        )),
                    ],
                ),
            ],
        ),
        migrations.RunPython(
            create_user_home_preference_table,
            delete_user_home_preference_table,
        ),
    ]
