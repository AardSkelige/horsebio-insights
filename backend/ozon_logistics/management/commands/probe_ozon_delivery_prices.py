"""Промер стоимости логистики Ozon по разным товарам и количествам.

Расчёт (`checkout`) ничего не создаёт и не стоит денег, поэтому им можно
безопасно измерить, как комиссия зависит от фасовки и количества — и понять,
покрывает ли её наш тариф для покупателя.
"""

import re
import time
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from ozon_logistics.models import OzonPickupPoint, OzonProduct
from ozon_logistics.services.client import (
    OzonLogisticsClient, OzonLogisticsError,
)
from ozon_logistics.services.oauth import OzonOAuthError

# Последние 4 цифры артикула — фасовка (граммы у порошков, штуки у капсул).
# Как вес это использовать нельзя, но для подбора «лёгкое/тяжёлое» годится.
PACK_RE = re.compile(r'(\d{4})$')
PAUSE_SECONDS = 0.3  # пауза между запросами: лимит Ozon 50 запросов в секунду


def _pack_size(offer_id):
    match = PACK_RE.search(offer_id or '')
    return int(match.group(1)) if match else None


class Command(BaseCommand):
    help = 'Промер комиссии Ozon за доставку по разным товарам и количествам'

    def add_arguments(self, parser):
        parser.add_argument('--phone', required=True,
                            help='Телефон покупателя с доступом к доставке Ozon')
        parser.add_argument('--point', type=int,
                            help='map_point_id пункта выдачи (по умолчанию — любой из кеша)')
        parser.add_argument('--offer-id', default='',
                            help='Артикулы через запятую вместо автоподбора')
        parser.add_argument('--limit', type=int, default=8,
                            help='Сколько товаров взять при автоподборе')
        parser.add_argument('--qty', default='1,3',
                            help='Количества через запятую')
        parser.add_argument('--tariff', type=Decimal, default=Decimal('250'),
                            help='Наш тариф для покупателя, ₽ — для сравнения')

    def handle(self, *args, **options):
        point_id = options['point'] or self._any_point()
        products = self._products(options['offer_id'], options['limit'])
        quantities = [int(q) for q in options['qty'].split(',') if q.strip()]
        client = OzonLogisticsClient()

        self.stdout.write(f'Пункт выдачи: {point_id}, товаров: {len(products)}, '
                          f'количества: {quantities}')
        self.stdout.write('')
        self.stdout.write(f'{"Артикул":<16}{"Фасовка":>9}{"Кол-во":>8}  '
                          f'{"Комиссия, ₽":>26}  Схема')
        self.stdout.write('-' * 76)

        results = []
        for product in products:
            for quantity in quantities:
                commission, schema, note = self._probe(
                    client, product, quantity, point_id, options['phone']
                )
                pack = _pack_size(product.offer_id)
                shown = str(commission) if commission is not None else note
                self.stdout.write(
                    f'{product.offer_id:<16}{pack if pack else "-":>9}{quantity:>8}  '
                    f'{shown:>26}  {schema}'
                )
                if commission is not None:
                    results.append((product.offer_id, pack, quantity, commission))
                time.sleep(PAUSE_SECONDS)

        self._summary(results, options['tariff'])

    def _any_point(self):
        point = OzonPickupPoint.objects.first()
        if point is None:
            raise CommandError(
                'В базе нет пунктов выдачи — запустите sync_ozon_pickup_points'
            )
        return point.map_point_id

    def _products(self, raw_offer_ids, limit):
        offer_ids = [o.strip() for o in raw_offer_ids.split(',') if o.strip()]
        if offer_ids:
            products = list(OzonProduct.objects.filter(offer_id__in=offer_ids))
            missing = set(offer_ids) - {p.offer_id for p in products}
            if missing:
                raise CommandError(f'Нет в каталоге Ozon: {", ".join(sorted(missing))}')
            return products

        # Автоподбор: разные фасовки, чтобы увидеть зависимость комиссии от них
        candidates = [
            p for p in OzonProduct.objects.filter(archived=False)
            if p.has_fbs_stocks or p.has_fbo_stocks
        ]
        if not candidates:
            raise CommandError('Нет товаров с остатками — запустите sync_ozon_products')

        candidates.sort(key=lambda p: (_pack_size(p.offer_id) or 0))
        if len(candidates) <= limit:
            return candidates
        # Берём равномерно по всему диапазону фасовок, а не первые подряд
        step = len(candidates) / limit
        return [candidates[int(i * step)] for i in range(limit)]

    def _probe(self, client, product, quantity, point_id, phone):
        try:
            response = client.checkout(
                phone=phone,
                items=[{'sku': product.sku, 'quantity': quantity}],
                map_point_id=point_id,
            )
        except (OzonOAuthError, OzonLogisticsError) as exc:
            return None, '', f'ошибка: {str(exc)[:60]}'

        total, schema, reason = Decimal('0'), '', ''
        available = False
        for split in response.get('splits') or []:
            schema = split.get('delivery_schema') or schema
            commissions = split.get('commissions')
            if not commissions:
                reason = split.get('unavailable_reason') or 'недоступно'
                continue
            available = True
            amount = (commissions.get('total') or {}).get('amount')
            if amount is not None:
                total += Decimal(str(amount))

        if not available:
            return None, schema, reason
        return total, schema, ''

    def _summary(self, results, tariff):
        self.stdout.write('')
        if not results:
            self.stdout.write(self.style.WARNING('Ни одного расчёта не получилось'))
            return

        commissions = [r[3] for r in results]
        smallest, largest = min(commissions), max(commissions)
        average = sum(commissions) / len(commissions)

        self.stdout.write(
            f'Комиссия Ozon: от {smallest} до {largest} ₽, в среднем '
            f'{average.quantize(Decimal("0.01"))} ₽ по {len(results)} расчётам'
        )
        self.stdout.write(f'Наш тариф: {tariff} ₽')

        losing = [r for r in results if r[3] > tariff]
        if losing:
            self.stdout.write(self.style.ERROR(
                f'Тариф не покрывает комиссию в {len(losing)} случаях из {len(results)}, '
                f'худший — {max(r[3] for r in losing)} ₽:'
            ))
            for offer_id, pack, quantity, commission in sorted(
                losing, key=lambda r: r[3], reverse=True
            )[:5]:
                self.stdout.write(f'  {offer_id} (фасовка {pack}) × {quantity} → {commission} ₽')
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Тариф покрывает все замеры, минимальный запас '
                f'{(tariff - largest).quantize(Decimal("0.01"))} ₽'
            ))
