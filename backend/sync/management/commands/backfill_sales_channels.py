# sync/management/commands/backfill_sales_channels.py
"""
Разовое проставление канала продаж у уже загруженных отгрузок.

Синхронизация сохраняет канал начиная с этой версии, но у отгрузок,
загруженных раньше, поле пустое. Команда добирает канал списочным запросом
к МойСкладу — без деталей документов, поэтому проходит период целиком за
несколько минут.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from sync.models import SalesChannel, Shipment
from sync.moysklad.connection import MoySkladAPIClient

logger = logging.getLogger(__name__)

# Обновляем отгрузки пачками: список id в одном запросе не должен
# разрастаться до размеров, которые не переварит PostgreSQL
UPDATE_BATCH = 500


class Command(BaseCommand):
    help = 'Проставляет канал продаж у отгрузок, загруженных до появления поля'

    def add_arguments(self, parser):
        parser.add_argument(
            '--months',
            type=int,
            default=12,
            help='За сколько последних месяцев обновить отгрузки (по умолчанию 12)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать, что будет обновлено, без записи в базу'
        )

    def handle(self, *args, **options):
        months = options['months']
        dry_run = options['dry_run']

        end_date = timezone.now()
        start_date = end_date - timedelta(days=months * 31)

        client = MoySkladAPIClient(settings.MOYSKLAD_TOKEN)

        self.stdout.write('Загружаю справочник каналов продаж…')
        channels = {}
        for row in client.get_sales_channels():
            channel, _ = SalesChannel.objects.update_or_create(
                external_id=row['id'],
                defaults={'name': row.get('name') or 'Без названия'},
            )
            channels[row['id']] = channel
        self.stdout.write(f'Каналов в МойСкладе: {len(channels)}')

        self.stdout.write(
            f'Загружаю отгрузки с {start_date.strftime("%d.%m.%Y")} — это займёт несколько минут…'
        )
        pairs = client.get_shipment_sales_channels(start_date, end_date)
        self.stdout.write(f'Отгрузок за период: {len(pairs)}')

        # Группируем по каналу: обновление идёт одним UPDATE на пачку id
        by_channel = {}
        without_channel = 0
        for shipment_id, channel_id in pairs:
            if not channel_id:
                without_channel += 1
                continue
            by_channel.setdefault(channel_id, []).append(shipment_id)

        updated = 0
        unknown_channels = set()
        for channel_id, shipment_ids in by_channel.items():
            channel = channels.get(channel_id)
            if not channel:
                # Канал удалён из МойСклада уже после отгрузки
                unknown_channels.add(channel_id)
                continue

            for i in range(0, len(shipment_ids), UPDATE_BATCH):
                batch = shipment_ids[i:i + UPDATE_BATCH]
                if dry_run:
                    updated += Shipment.objects.filter(external_id__in=batch).count()
                else:
                    updated += Shipment.objects.filter(external_id__in=batch).update(
                        sales_channel=channel
                    )

        prefix = 'DRY RUN: ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Обновлено отгрузок: {updated}'
        ))
        if without_channel:
            self.stdout.write(f'Без канала в МойСкладе: {without_channel}')
        if unknown_channels:
            self.stdout.write(self.style.WARNING(
                f'Каналов не найдено в справочнике: {len(unknown_channels)}'
            ))
