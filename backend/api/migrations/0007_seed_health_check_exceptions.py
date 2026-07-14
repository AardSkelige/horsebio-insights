from django.db import migrations


def seed_exceptions(apps, schema_editor):
    """Перенести существующие data/*.json исключения в БД (одноразово, идемпотентно)."""
    from api.services.health_checks import import_exceptions_from_files
    Model = apps.get_model('api', 'HealthCheckException')
    import_exceptions_from_files(Model)


def unseed(apps, schema_editor):
    Model = apps.get_model('api', 'HealthCheckException')
    Model.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_checkrunresult_healthcheckexception_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_exceptions, unseed),
    ]
