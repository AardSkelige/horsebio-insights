"""Обновляет сопоставление артикулов с sku в Ozon."""

from django.core.management.base import BaseCommand

from ozon_logistics.services.catalog import sync_products
from ozon_logistics.services.client import OzonLogisticsError
from ozon_logistics.services.oauth import OzonOAuthError


class Command(BaseCommand):
    help = 'Синхронизация товаров Ozon (offer_id → sku) для Ozon Доставки'

    def handle(self, *args, **options):
        try:
            stats = sync_products()
        except (OzonOAuthError, OzonLogisticsError) as exc:
            self.stderr.write(self.style.ERROR(f'Ozon недоступен: {exc}'))
            return

        self.stdout.write(
            'Получено из Ozon: {fetched}, создано: {created}, обновлено: {updated}'.format(**stats)
        )
        if stats['skipped_without_sku']:
            self.stdout.write(
                self.style.WARNING(f"Без sku и пропущено: {stats['skipped_without_sku']}")
            )
        self.stdout.write(
            self.style.SUCCESS(
                'Всего в таблице: {total_stored}, годны для Ozon Доставки '
                '(остаток FBS, не архив): {sellable}'.format(**stats)
            )
        )
