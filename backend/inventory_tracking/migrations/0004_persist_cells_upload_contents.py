import django.db.models.deletion
from django.db import migrations, models


def copy_month_from_run(apps, schema_editor):
    CellsUploadLog = apps.get_model('inventory_tracking', 'CellsUploadLog')
    for upload in CellsUploadLog.objects.select_related('run').iterator():
        upload.month_start = upload.run.month_start
        upload.save(update_fields=['month_start'])


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_tracking', '0003_cellsuploadlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='cellsuploadlog',
            name='codes',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='cellsuploadlog',
            name='month_start',
            field=models.DateField(db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='cellsuploadlog',
            name='run',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cells_uploads',
                to='inventory_tracking.inventoryrun',
            ),
        ),
        migrations.RunPython(copy_month_from_run, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='cellsuploadlog',
            name='month_start',
            field=models.DateField(db_index=True),
        ),
    ]
