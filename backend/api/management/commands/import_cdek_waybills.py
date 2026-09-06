# api/management/commands/import_cdek_waybills.py
"""
Перенос состояния робота накладных СДЭК из JSON-файла в базу.

Разовый шаг переезда (MIGRATION-PLAN.md, этап 6), но команда идемпотентна:
повторный запуск не задваивает записи и не портит уже перенесённые. Так и
задумано — переносить можно до выката робота, проверять и переносить снова.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.models import CdekWaybillState

DEFAULT_PATH = (
    '/app/moysklad/horsebio/01_daemons/07_cdek_waybills/data/.cdek_waybill_state.json'
)


class Command(BaseCommand):
    help = 'Перенести состояние робота накладных СДЭК из файла в базу'

    def add_arguments(self, parser):
        parser.add_argument('--path', default=DEFAULT_PATH,
                            help='Файл состояния (по умолчанию — том робота)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать, что будет перенесено, и ничего не писать')

    def handle(self, *args, **options):
        path = Path(options['path'])
        if not path.exists():
            raise CommandError(f'Файл состояния не найден: {path}')

        try:
            state = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            raise CommandError(f'Файл состояния не читается: {e}') from e

        orders = state.get('orders') or {}
        if not orders:
            self.stdout.write(self.style.WARNING('В файле нет ни одной записи'))
            return

        created = updated = unchanged = 0
        for order_id, payload in orders.items():
            existing = CdekWaybillState.objects.filter(order_id=order_id).first()
            if existing is None:
                created += 1
                if not options['dry_run']:
                    CdekWaybillState.objects.create(order_id=order_id, payload=payload)
            elif existing.payload != payload:
                updated += 1
                if not options['dry_run']:
                    existing.payload = payload
                    existing.save(update_fields=['payload', 'updated_at'])
            else:
                unchanged += 1

        prefix = 'Будет перенесено' if options['dry_run'] else 'Перенесено'
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}: заведено {created}, обновлено {updated}, без изменений {unchanged}'
        ))
