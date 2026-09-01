"""Обновляет статусы отправлений Ozon по созданным нами заказам."""

from django.core.management.base import BaseCommand

from ozon_logistics.services.client import OzonLogisticsError
from ozon_logistics.services.oauth import OzonOAuthError
from ozon_logistics.services.tracking import postings_needing_attention, sync_postings


class Command(BaseCommand):
    help = 'Статусы отправлений Ozon Доставки'

    def handle(self, *args, **options):
        try:
            stats = sync_postings()
        except (OzonOAuthError, OzonLogisticsError) as exc:
            self.stderr.write(self.style.ERROR(f'Ozon недоступен: {exc}'))
            return

        self.stdout.write(
            'Заказов под наблюдением: {quotes}, отправлений получено: {seen}'.format(**stats)
        )

        alarming = postings_needing_attention()
        if alarming:
            self.stdout.write(self.style.ERROR(
                f'Требуют внимания: {alarming.count()} — товар не доехал, '
                'деньги покупателю нужно вернуть:'
            ))
            for posting in alarming[:20]:
                site_order = posting.quote.site_order_id if posting.quote else '—'
                self.stdout.write(
                    f'  {posting.posting_number} · {posting.status} · '
                    f'заказ сайта {site_order} · {posting.cancel_reason or "без причины"}'
                )
        else:
            self.stdout.write(self.style.SUCCESS('Всё в порядке, вмешательства не требуется'))
