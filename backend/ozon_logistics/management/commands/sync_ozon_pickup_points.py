"""Обновляет локальную копию пунктов выдачи Ozon."""

from django.core.management.base import BaseCommand

from ozon_logistics.services.client import OzonLogisticsError
from ozon_logistics.services.oauth import OzonOAuthError
from ozon_logistics.services.pickup_points import sync_pickup_points


class Command(BaseCommand):
    help = 'Синхронизация пунктов выдачи Ozon для карты в корзине'

    def handle(self, *args, **options):
        try:
            stats = sync_pickup_points()
        except (OzonOAuthError, OzonLogisticsError) as exc:
            self.stderr.write(self.style.ERROR(f'Ozon недоступен: {exc}'))
            return

        self.stdout.write(
            'Получено из Ozon: {fetched}, создано: {created}, обновлено: {updated}'.format(**stats)
        )
        if stats['skipped']:
            self.stdout.write(self.style.WARNING(f"Без координат и пропущено: {stats['skipped']}"))
        self.stdout.write(
            self.style.SUCCESS(f"Всего пунктов в таблице: {stats['total_stored']}")
        )
