"""Забирает возвраты по отправлениям Ozon Доставки."""

from django.core.management.base import BaseCommand

from ozon_logistics.services.client import OzonLogisticsError
from ozon_logistics.services.oauth import OzonOAuthError
from ozon_logistics.services.returns import returns_needing_attention, sync_returns


class Command(BaseCommand):
    help = 'Возвраты по заказам Ozon Доставки'

    def handle(self, *args, **options):
        try:
            stats = sync_returns()
        except (OzonOAuthError, OzonLogisticsError) as exc:
            self.stderr.write(self.style.ERROR(f'Ozon недоступен: {exc}'))
            return

        self.stdout.write(
            'Отправлений под наблюдением: {postings}, возвратов получено: {seen}'.format(**stats)
        )

        pending = returns_needing_attention()
        if pending:
            self.stdout.write(self.style.ERROR(
                f'Не разобрано возвратов: {pending.count()} — принять товар и вернуть деньги:'
            ))
            for item in pending[:20]:
                site_order = item.quote.site_order_id if item.quote else '—'
                self.stdout.write(
                    f'  {item.return_id} · отправление {item.posting_number} · '
                    f'заказ сайта {site_order} · {item.reason or "причина не указана"}'
                )
        else:
            self.stdout.write(self.style.SUCCESS('Неразобранных возвратов нет'))
