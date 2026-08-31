"""Создаёт заказы в Ozon по оплаченным заказам сайта."""

from django.core.management.base import BaseCommand

from ozon_logistics.services.site_orders import process_paid_orders


class Command(BaseCommand):
    help = 'Заказы Ozon по оплаченным заказам сайта с доставкой Ozon'

    def handle(self, *args, **options):
        stats = process_paid_orders()

        self.stdout.write(
            'Заказов сайта с доставкой Ozon: {checked}, '
            'создано в Ozon: {created}, пропущено: {skipped}'.format(**stats)
        )
        if stats['failed']:
            self.stdout.write(
                self.style.ERROR(f"Не удалось создать: {stats['failed']} — смотрите лог")
            )
        else:
            self.stdout.write(self.style.SUCCESS('Ошибок нет'))
