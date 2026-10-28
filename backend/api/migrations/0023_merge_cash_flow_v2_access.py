from django.db import migrations


def merge_cash_flow_v2(apps, schema_editor):
    UserPageAccess = apps.get_model('api', 'UserPageAccess')
    v2_rows = UserPageAccess.objects.filter(page_key='cash-flow-v2')
    UserPageAccess.objects.bulk_create(
        [UserPageAccess(user_id=user_id, page_key='cash-flow')
         for user_id in v2_rows.values_list('user_id', flat=True)],
        ignore_conflicts=True,
    )
    v2_rows.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_push_notifications'),
    ]

    operations = [
        migrations.RunPython(merge_cash_flow_v2, migrations.RunPython.noop),
    ]
