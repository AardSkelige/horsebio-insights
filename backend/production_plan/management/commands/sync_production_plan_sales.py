from django.core.management.base import BaseCommand
from django.utils import timezone

from production_plan.services import ozon_sales, wb_sales
from production_plan.services.plan import full_months


class Command(BaseCommand):
    help = 'Подтянуть продажи Ozon и заказы WB для производственного плана'

    def handle(self, *args, **options):
        for month, total in ozon_sales.sync(full_months(timezone.localdate())).items():
            self.stdout.write(self.style.SUCCESS(f'Ozon {month:%m.%Y}: {total} шт'))
        if wb_sales.configured():
            total = wb_sales.sync(timezone.localdate())
            self.stdout.write(self.style.SUCCESS(f'WB: заказов за {wb_sales.HISTORY_DAYS} дней {total}, история с {wb_sales.covered_from():%d.%m.%Y}'))
        else:
            self.stdout.write('WB: нет WB_STATS_TOKEN, WB считается по отгрузкам')
