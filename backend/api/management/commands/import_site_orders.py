# api/management/commands/import_site_orders.py
"""
Перенос копии заказов сайта из JSON-файла в базу.

Разовый шаг переезда (MIGRATION-PLAN.md, этап 6), но команда идемпотентна:
повторный запуск ничего не задваивает. Осторожность здесь не лишняя — это
единственная копия заказов: подтверждённое окно сайт больше не отдаёт.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import SiteOrderSnapshot, SiteOrdersReconcileState

DEFAULT_PATH = '/app/moysklad/horsebio/02_checks/02_site_orders/data/site_orders.json'


class Command(BaseCommand):
    help = 'Перенести копию заказов сайта из файла в базу'

    def add_arguments(self, parser):
        parser.add_argument('--path', default=DEFAULT_PATH,
                            help='Файл хранилища (по умолчанию — том сверки)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать, что будет перенесено, и ничего не писать')

    def handle(self, *args, **options):
        path = Path(options['path'])
        if not path.exists():
            raise CommandError(f'Хранилище не найдено: {path}')

        try:
            store = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            # Ровно та же осторожность, что и в самой сверке: молча начать
            # с пустого нельзя, второй копии заказов нет.
            raise CommandError(
                f'Хранилище повреждено ({path}): {e}. Чинить руками, не удалять.'
            ) from e

        orders = store.get('orders') or {}
        if not orders:
            raise CommandError('В хранилище нет ни одного заказа — переносить нечего')

        created = updated = unchanged = 0
        for order_id, payload in orders.items():
            existing = SiteOrderSnapshot.objects.filter(order_id=order_id).first()
            if existing is None:
                created += 1
            elif existing.payload != payload:
                updated += 1
            else:
                unchanged += 1

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                f'Будет перенесено: заведено {created}, обновлено {updated}, '
                f'без изменений {unchanged}; отметки '
                f'{store.get("last_fetch")} / {store.get("last_acknowledge")}'
            ))
            return

        with transaction.atomic():
            for order_id, payload in orders.items():
                SiteOrderSnapshot.objects.update_or_create(
                    order_id=order_id,
                    defaults={'payload': payload, 'date': (payload or {}).get('date') or ''},
                )
            # Отметки двигаем только вперёд. Команду можно запустить и после
            # того, как сверка уже отработала: откат отметки назад означал бы
            # находку «сайт давно не отдаёт заказы» на исправно работающем сайте.
            marks = SiteOrdersReconcileState.get()
            marks.last_fetch = max(marks.last_fetch or '', store.get('last_fetch') or '')
            marks.last_acknowledge = max(marks.last_acknowledge or '',
                                         store.get('last_acknowledge') or '')
            marks.save(update_fields=['last_fetch', 'last_acknowledge'])

        self.stdout.write(self.style.SUCCESS(
            f'Перенесено: заведено {created}, обновлено {updated}, без изменений {unchanged}'
        ))
        self.stdout.write(f'Отметки сверки: выгрузка {marks.last_fetch or "—"}, '
                          f'подтверждение {marks.last_acknowledge or "—"}')
