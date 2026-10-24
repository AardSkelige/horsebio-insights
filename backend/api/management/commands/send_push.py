from django.core.management.base import BaseCommand

from api.notifications.push import dispatch


class Command(BaseCommand):
    help = 'Разослать пуши о новых уведомлениях тем, кто их включил'

    def handle(self, *args, **options):
        stats = dispatch()
        self.stdout.write(
            f'Подписанных людей: {stats["users"]}, отправлено: {stats["pushed"]}, не дошло: {stats["failed"]}'
        )
