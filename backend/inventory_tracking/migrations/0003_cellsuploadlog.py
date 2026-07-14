from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_tracking', '0002_productinventorystatus_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='CellsUploadLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inventory_name', models.CharField(max_length=50)),
                ('inventory_date', models.DateField()),
                ('warehouse', models.CharField(blank=True, max_length=255)),
                ('matched_count', models.IntegerField(default=0)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('run', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cells_uploads',
                    to='inventory_tracking.inventoryrun',
                )),
            ],
            options={'ordering': ['inventory_date']},
        ),
    ]
