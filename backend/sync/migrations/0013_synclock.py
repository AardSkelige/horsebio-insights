# Generated manually for SyncLock model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('parser', '0012_remove_rawmaterialusage_parser_rawm_shipmen_169635_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='SyncLock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lock_type', models.CharField(choices=[('moysklad_sync', 'Синхронизация МойСклад')], max_length=50, unique=True, verbose_name='Тип блокировки')),
                ('is_locked', models.BooleanField(default=False, verbose_name='Заблокировано')),
                ('locked_at', models.DateTimeField(blank=True, null=True, verbose_name='Время блокировки')),
                ('locked_by', models.CharField(blank=True, max_length=255, null=True, verbose_name='Источник блокировки')),
            ],
            options={
                'verbose_name': 'Блокировка синхронизации',
                'verbose_name_plural': 'Блокировки синхронизации',
            },
        ),
    ]
