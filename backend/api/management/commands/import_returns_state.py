# api/management/commands/import_returns_state.py
"""
Перенос состояния монитора возвратов из JSON-файла в базу.

Разовый шаг переезда (MIGRATION-PLAN.md, этап 6), но команда идемпотентна:
её можно запускать повторно, в том числе после выката монитора, — она подберёт
отметки, которые он успел дописать в файл.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import ReturnProcessedOrder, ReturnsMonitorState

DEFAULT_PATH = '/app/moysklad/horsebio/01_daemons/03_returns/data/.returns_state.json'


class Command(BaseCommand):
    help = 'Перенести состояние монитора возвратов из файла в базу'

    def add_arguments(self, parser):
        parser.add_argument('--path', default=DEFAULT_PATH,
                            help='Файл состояния (по умолчанию — том монитора)')
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

        processed = state.get('processed_orders') or {}
        if not processed:
            raise CommandError('В файле нет ни одной отметки — переносить нечего')

        known = set(ReturnProcessedOrder.objects.values_list('order_id', flat=True))
        fresh = [order_id for order_id in processed if order_id not in known]
        last_run = str(state.get('last_run') or '')[:32]

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                f'Будет перенесено: новых {len(fresh)} из {len(processed)} '
                f'(в базе уже {len(known)}); последний прогон в файле — {last_run or "—"}'
            ))
            return

        with transaction.atomic():
            ReturnProcessedOrder.objects.bulk_create(
                [ReturnProcessedOrder(order_id=order_id, payload=payload)
                 for order_id, payload in processed.items()],
                update_conflicts=True,
                unique_fields=['order_id'],
                update_fields=['payload', 'updated_at'],
            )
            # Отметку «докуда дошли» двигаем только вперёд: команду можно
            # запустить и после прогона монитора, а откат назад заставил бы его
            # перебирать заказы, которые он уже разобрал.
            marks = ReturnsMonitorState.get()
            marks.last_run = max(marks.last_run or '', last_run)
            marks.save(update_fields=['last_run'])

        self.stdout.write(self.style.SUCCESS(
            f'Перенесено: новых {len(fresh)}, перезаписано {len(processed) - len(fresh)}; '
            f'всего в базе {ReturnProcessedOrder.objects.count()}'
        ))
        self.stdout.write(f'Последний прогон: {ReturnsMonitorState.get().last_run or "—"}')
