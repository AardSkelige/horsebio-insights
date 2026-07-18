from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_rawmaterial_lead_time_period_months'),
    ]

    operations = [
        migrations.AddField(
            model_name='synclock',
            name='lock_token',
            field=models.UUIDField(blank=True, editable=False, null=True, verbose_name='Токен владельца'),
        ),
    ]
