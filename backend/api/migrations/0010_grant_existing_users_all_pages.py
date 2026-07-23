"""
Разово выдаёт всем текущим активным не-суперпользователям доступ ко всем
назначаемым страницам. Так переход на постраничные права («по умолчанию
ничего») не отбирает доступ у уже работающих пользователей — правило
«ничего по умолчанию» действует только для новых учёток.
"""
from django.db import migrations


def grant_all_pages(apps, schema_editor):
    from api.access import ASSIGNABLE_PAGE_KEYS

    User = apps.get_model('auth', 'User')
    UserPageAccess = apps.get_model('api', 'UserPageAccess')

    rows = []
    for user in User.objects.filter(is_active=True, is_superuser=False):
        for key in ASSIGNABLE_PAGE_KEYS:
            rows.append(UserPageAccess(user_id=user.id, page_key=key))

    UserPageAccess.objects.bulk_create(rows, ignore_conflicts=True)


def noop_reverse(apps, schema_editor):
    # Откат не удаляет выданные права — безопаснее оставить доступ как есть.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_userpageaccess'),
    ]

    operations = [
        migrations.RunPython(grant_all_pages, noop_reverse),
    ]
