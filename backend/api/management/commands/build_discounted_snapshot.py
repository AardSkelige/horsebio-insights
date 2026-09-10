# api/management/commands/build_discounted_snapshot.py
"""
Собрать снимок раздела «Уценка» и положить его в базу.

Запускается по расписанию (реестр проверок, `horsebio_discounted_snapshot`)
и кнопкой «Обновить» на самой странице. Смысл — держать МойСклад вне запроса
пользователя: страница и уведомления читают снимок из базы, а сюда сходить
и подождать одиннадцать запросов может фоновая задача.

Расчёт живёт в api/views/discounted.py — там же, где ручки раздела. Разложить
его по слоям стоит, но это отдельная работа: на сборку завязаны и экспорт,
и снятие с продажи, и тесты.
"""
from django.core.management.base import BaseCommand

from api.models import SectionSnapshot


class Command(BaseCommand):
    help = 'Пересобрать снимок раздела «Уценка» из МойСклад'

    def handle(self, *args, **options):
        from api.views.discounted import SECTION_KEY, build_snapshot

        payload = build_snapshot()

        summary = payload.get('summary') or {}
        self.stdout.write(self.style.SUCCESS(
            'Снимок собран: позиций {positions}, единиц {units}, требуют действия {needs_action}'.format(
                positions=summary.get('positions', 0),
                units=summary.get('units', 0),
                needs_action=summary.get('needs_action', 0),
            )
        ))
        stored = SectionSnapshot.stored(SECTION_KEY)
        self.stdout.write(f"Собран: {stored.updated_at:%d.%m.%Y %H:%M}")
