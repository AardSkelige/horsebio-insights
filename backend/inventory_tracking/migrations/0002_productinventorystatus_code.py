from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory_tracking', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='productinventorystatus',
            name='code',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
