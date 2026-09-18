"""Возврат от Озона по заказу, который отгрузили руками до появления робота.

Робот такие заказы не подхватит: он видит, что вопрос с отгрузкой закрыт
(статус «Отгружен», отгрузка есть), и больше к ним не возвращается. А возврат
им всё равно нужен — иначе товар, уехавший со склада FBO, останется списанным
дважды: один раз при поставке на Ozon, второй раз отгрузкой покупателю.

Без --apply только рассказывает, что создал бы.
"""

from django.core.management.base import BaseCommand, CommandError

from ozon_logistics.models import OzonDeliveryQuote
from ozon_logistics.services import ms_client, ms_orders, ms_returns


class Command(BaseCommand):
    help = 'Разовый возврат от Озона по заказу сайта, отгруженному вручную'

    def add_arguments(self, parser):
        parser.add_argument('site_order_id', help='номер заказа сайта (externalCode в МойСкладе)')
        parser.add_argument('--apply', action='store_true', help='создать документ, а не рассказать')

    def handle(self, *args, **options):
        site_order_id = options['site_order_id']
        apply = options['apply']

        quote = (
            OzonDeliveryQuote.objects
            .filter(site_order_id=site_order_id, status=OzonDeliveryQuote.STATUS_ORDERED)
            .first()
        )
        if quote is None:
            raise CommandError(f'по заказу сайта {site_order_id} нет созданного заказа Ozon')
        if quote.ms_return:
            self.stdout.write(self.style.WARNING(
                f'Возврат по этому заказу уже создан: {quote.ms_return}'
            ))
            return

        postings = sorted(quote.postings_tracked.all(), key=lambda p: p.posting_number)
        products = ms_returns.fbo_products(postings)
        if not products:
            raise CommandError(
                'в заказе нет отправлений со склада FBO — возврат не нужен'
            )

        self.stdout.write(f'Заказ Ozon {quote.order_number}, уехало со склада FBO:')
        for article, quantity in sorted(products.items()):
            self.stdout.write(f'  {article} × {quantity:g}')

        try:
            payload = ms_returns.payload_for(quote, postings)
            if not apply:
                # Показываем документ целиком: на боевых данных лучше сперва посмотреть
                self.stdout.write('\nСоздал бы возврат покупателя:')
                self.stdout.write(f"  основание: отгрузка {payload['demand']['meta']['href'].rsplit('/', 1)[-1]}")
                for position in payload['positions']:
                    self.stdout.write(
                        f"  позиция: {position['quantity']:g} шт по "
                        f"{position['price'] / 100:.2f} ₽, НДС {position['vat']}"
                    )
                self.stdout.write('  комментарий:')
                for line in payload['description'].split('\n'):
                    self.stdout.write(f'    {line}')
            name = ms_returns.ensure_return(quote, postings, apply=apply, payload=payload)
        except ms_returns.ReturnNotPossible as exc:
            raise CommandError(f'возврат собрать не вышло: {exc}') from exc
        except ms_client.MoyskladError as exc:
            raise CommandError(f'МойСклад отказал: {exc}') from exc

        if not apply:
            self.stdout.write(self.style.WARNING(
                'Это прогон вхолостую. Повторите с --apply, чтобы создать документ.'
            ))
            return

        OzonDeliveryQuote.objects.filter(pk=quote.pk).update(ms_return=name)
        quote.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(f'Создан возврат от Озона {name}'))

        # Комментарий заказа переписываем той же функцией, что и робот, — чтобы
        # текст был один в один и робот потом не переписывал его по-своему.
        order = ms_client.order_by_external_code(site_order_id)
        if order is None:
            self.stdout.write(self.style.WARNING(
                f'Заказа {site_order_id} нет в МойСкладе — комментарий не тронут'
            ))
            return

        block = ms_orders.build_block(quote, postings)
        description = order.get('description') or ''
        merged = ms_orders.merge_description(description, block)
        if merged != description:
            ms_client.put(f"/entity/customerorder/{order['id']}", {'description': merged})
            self.stdout.write(self.style.SUCCESS(f'Комментарий заказа {order.get("name")} обновлён'))
        OzonDeliveryQuote.objects.filter(pk=quote.pk).update(ms_note='\n'.join(block))
