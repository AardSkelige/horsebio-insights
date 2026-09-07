# api/management/commands/import_order_emails.py
"""
Перенос журнала заказов из писем в базу.

Разовый шаг переезда (MIGRATION-PLAN.md, этап 6), но команда идемпотентна:
её можно запускать повторно, в том числе после выката роботов, — она подберёт
то, что они успели дописать в файл.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import OrderEmailMessage, OrderEmailOrder, OrderEmailState

DEFAULT_PATH = ('/app/moysklad/horsebio/01_daemons/06_order_email_sync/data/'
                '.order_email_state.json')


class Command(BaseCommand):
    help = 'Перенести журнал заказов из писем в базу'

    def add_arguments(self, parser):
        parser.add_argument('--path', default=DEFAULT_PATH,
                            help='Файл журнала (по умолчанию — том роботов)')
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать, что будет перенесено, и ничего не писать')

    def handle(self, *args, **options):
        path = Path(options['path'])
        if not path.exists():
            raise CommandError(f'Файл журнала не найден: {path}')

        try:
            state = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            raise CommandError(f'Файл журнала не читается: {e}') from e

        orders = state.get('orders') or {}
        messages = [str(mid) for mid in (state.get('processed_message_ids') or [])]
        if not orders and not messages:
            raise CommandError('В файле нет ни заказов, ни писем — переносить нечего')

        known_orders = set(OrderEmailOrder.objects.values_list('order_id', flat=True))
        known_messages = set(OrderEmailMessage.objects.values_list('message_id', flat=True))
        fresh_orders = [oid for oid in orders if oid not in known_orders]
        fresh_messages = [mid for mid in messages if mid not in known_messages]
        last_checked = str(state.get('last_checked_date') or '')[:32]

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(
                f'Будет перенесено: заказов {len(fresh_orders)} новых из {len(orders)}, '
                f'писем {len(fresh_messages)} новых из {len(messages)}; '
                f'проверено по {last_checked or "—"}'
            ))
            return

        with transaction.atomic():
            if orders:
                OrderEmailOrder.objects.bulk_create(
                    [OrderEmailOrder(order_id=order_id, payload=payload)
                     for order_id, payload in orders.items()],
                    update_conflicts=True,
                    unique_fields=['order_id'],
                    update_fields=['payload', 'updated_at'],
                )
            if messages:
                OrderEmailMessage.objects.bulk_create(
                    [OrderEmailMessage(message_id=mid) for mid in messages],
                    ignore_conflicts=True,
                )
            # Дату проверки двигаем только вперёд: команду можно запустить и
            # после прогона робота, а откат назад заставил бы его перечитывать
            # уже разобранную почту.
            marks = OrderEmailState.get()
            marks.last_checked_date = max(marks.last_checked_date or '', last_checked)
            marks.save(update_fields=['last_checked_date', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            f'Перенесено: заказов новых {len(fresh_orders)}, писем новых {len(fresh_messages)}; '
            f'всего в базе — заказов {OrderEmailOrder.objects.count()}, '
            f'писем {OrderEmailMessage.objects.count()}'
        ))
