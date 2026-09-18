"""Обновляет статусы отправлений Ozon по созданным нами заказам.

Тем же прогоном переносит номер заказа и отправлений в заказ МойСклада: свежие
статусы нужны обеим задачам, а ходить в Ozon дважды незачем.
"""

from django.core.management.base import BaseCommand

from ozon_logistics.services import ms_orders
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
        for error in stats.get('errors') or []:
            self.stderr.write(self.style.ERROR(f'Отправления получены не все — {error}'))

        self._sync_moysklad()

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

    def _sync_moysklad(self):
        """Сведения о доставке — в заказ МойСклада.

        МойСклад может быть недоступен, но статусы к этому моменту уже собраны:
        валить из-за этого весь прогон нельзя, иначе отмену посылки мы увидим
        не раньше, чем МойСклад оживёт.
        """
        try:
            written = ms_orders.sync_orders()
        except ms_orders.MoyskladError as exc:
            self.stderr.write(self.style.ERROR(f'МойСклад недоступен: {exc}'))
            return

        self.stdout.write(
            'Заказов МойСклада обновлено: {written}, уже в порядке: {unchanged}, '
            'ещё не заведено: {missing}, отгружено: {shipped}'.format(**written)
        )
        if written['by_hand']:
            self.stdout.write(self.style.WARNING(
                f'Ждут человека: {written["by_hand"]} — товар уехал со склада Ozon, '
                'а возврат от Озона собрать не вышло'
            ))
        for error in written.get('errors') or []:
            self.stderr.write(self.style.ERROR(f'Заказ не обновлён — {error}'))
