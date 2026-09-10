"""
Таблица кеша.

Кеш переехал из файлов в базу (config/settings.py). Таблицу заводим миграцией,
а не командой `createcachetable` руками: деплой применяет миграции сам, и кеш
не должен зависеть от того, вспомнил ли кто-то про отдельный шаг — ровно та же
забывчивость, из-за которой раньше терялось состояние роботов.

Команду зовём вместо своего CREATE TABLE: она знает про различия SQLite
и Postgres и ничего не делает, если таблица уже есть.
"""
from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command('createcachetable', database=schema_editor.connection.alias, verbosity=0)


def drop_cache_table(apps, schema_editor):
    schema_editor.execute('DROP TABLE IF EXISTS django_cache')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0018_sectionsnapshot'),
    ]

    operations = [
        migrations.RunPython(create_cache_table, drop_cache_table),
    ]
