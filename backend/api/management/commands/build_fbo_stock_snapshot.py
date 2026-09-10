# api/management/commands/build_fbo_stock_snapshot.py
"""
Собрать снимок раздела «Остатки для FBO» и положить его в базу.

Запускается по расписанию (реестр проверок, `horsebio_fbo_stock_snapshot`)
и кнопкой «Обновить» на странице. Смысл тот же, что у уценки: держать МойСклад
вне запроса пользователя — страница читает снимок, а ждать четыре запроса
к чужому API может фоновая задача.
"""
from django.core.management.base import BaseCommand

from api.models import SectionSnapshot


class Command(BaseCommand):
    help = 'Пересобрать снимок раздела «Остатки для FBO» из МойСклад'

    def handle(self, *args, **options):
        from api.views.fbo_stock import SECTION_KEY, build_snapshot

        payload = build_snapshot()

        items = payload.get('items') or []
        on_stock = [item for item in items if not item['is_empty']]
        below = [item for item in items if item.get('below_minimum')]
        self.stdout.write(self.style.SUCCESS(
            f'Снимок собран: позиций {len(items)}, с остатком {len(on_stock)}, '
            f'ниже минимума {len(below)}'
        ))
        stored = SectionSnapshot.stored(SECTION_KEY)
        self.stdout.write(f'Собран: {stored.updated_at:%d.%m.%Y %H:%M}')
