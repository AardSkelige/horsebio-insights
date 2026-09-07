# api/management/commands/import_buy_price_history.py
"""
Перенос истории прогонов робота закупочных цен из JSON-файла в базу.

Разовый шаг переезда (MIGRATION-PLAN.md, этап 6), но команда идемпотентна:
её можно запускать повторно, в том числе после выката робота, — она подберёт
прогоны, которые тот успел дописать в файл.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import BuyPriceSyncRun

DEFAULT_PATH = '/app/moysklad/horsebio/01_daemons/02_buy_prices/data/.sync_state.json'


class Command(BaseCommand):
    help = 'Перенести историю прогонов робота закупочных цен из файла в базу'

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

        # Дату приводим к тому же виду, в каком она ляжет в базу, один раз —
        # иначе сравнение «уже есть?» идёт с одной строкой, а запись с другой,
        # и счётчики в отчёте разъезжаются.
        history = [dict(run, date=str(run['date'])[:32])
                   for run in (state.get('history') or []) if run.get('date')]
        if not history:
            raise CommandError('В файле нет ни одного прогона — переносить нечего')

        known = set(BuyPriceSyncRun.objects.values_list('date', flat=True))
        fresh = [run for run in history if run['date'] not in known]

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                f'Будет перенесено прогонов: {len(fresh)} новых из {len(history)} '
                f'(в базе уже {len(known)}); последний в файле — {history[-1]["date"]}'
            ))
            return

        with transaction.atomic():
            BuyPriceSyncRun.objects.bulk_create(
                [
                    BuyPriceSyncRun(
                        date=run['date'],
                        stats=run.get('stats') or {},
                        changes=run.get('changes') or [],
                        errors=run.get('errors') or [],
                    )
                    for run in history
                ],
                update_conflicts=True,
                unique_fields=['date'],
                update_fields=['stats', 'changes', 'errors'],
            )

        self.stdout.write(self.style.SUCCESS(
            f'Перенесено: заведено {len(fresh)}, обновлено {len(history) - len(fresh)}; '
            f'всего в базе {BuyPriceSyncRun.objects.count()}'
        ))
