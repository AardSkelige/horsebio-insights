# api/management/commands/import_payment_deadlines.py
"""
Перенос снимка сроков оплаты из файла в базу.

Снимок робот пересобирает каждый прогон, так что перенос нужен ровно затем,
чтобы страница не осталась пустой между выкатом и ближайшим ночным прогоном.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.models import PaymentDeadlineSnapshot

DEFAULT_PATH = ('/app/moysklad/horsebio/01_daemons/05_payment_deadline/data/deadlines.json')


class Command(BaseCommand):
    help = 'Перенести снимок сроков оплаты из файла в базу'

    def add_arguments(self, parser):
        parser.add_argument('--path', default=DEFAULT_PATH,
                            help='Файл снимка (по умолчанию — том робота)')

    def handle(self, *args, **options):
        path = Path(options['path'])
        if not path.exists():
            raise CommandError(f'Файл снимка не найден: {path}')

        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            raise CommandError(f'Файл снимка не читается: {e}') from e

        if not payload.get('generated_at'):
            raise CommandError('Это не похоже на снимок: нет отметки generated_at')

        PaymentDeadlineSnapshot.store(payload)
        summary = payload.get('summary') or {}
        self.stdout.write(self.style.SUCCESS(
            f'Перенесён снимок от {payload["generated_at"]}: {summary or "без сводки"}'
        ))
