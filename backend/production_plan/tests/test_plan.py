from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from core.models import Counterparty, Product, Shipment, ShipmentItem
from production_plan.models import OzonMonthSales, WbOrder, WbSync
from production_plan.services.plan import build, collect_sales, full_months

JUL, AUG, SEP = date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)
MONTHS = [JUL, AUG, SEP]


def stock(article, name='Товар', quantity=0, in_transit=0):
    return {'article': article, 'name': name, 'quantity': quantity, 'in_transit': in_transit}


def sales(article, *values, key='ozon'):
    return {article: {key: dict(zip(MONTHS, values))}}


class FullMonthsTests(SimpleTestCase):
    def test_three_full_months_before_today(self):
        self.assertEqual(full_months(date(2026, 10, 21)), MONTHS)

    def test_crosses_new_year(self):
        self.assertEqual(full_months(date(2026, 2, 3)), [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)])


class BuildTests(SimpleTestCase):
    def row(self, item, sold, rules=(), green=()):
        rows = build(MONTHS, sold, [item], list(rules), set(green))
        return rows[0] if rows else None

    def test_two_months_of_usual_sales_minus_stock_and_production(self):
        row = self.row(stock('11-01AP0500', quantity=100, in_transit=50), sales('11-01AP0500', 175, 35, 203))
        self.assertEqual(row['usual'], 175)
        self.assertEqual(row['need'], 350)
        self.assertEqual(row['produce'], 200)
        self.assertEqual(row['days'], 17)
        self.assertEqual(row['status'], 'urgent')

    def test_one_spike_does_not_inflate_the_plan(self):
        row = self.row(stock('A-1', quantity=0), sales('A-1', 600, 100, 110))
        self.assertEqual(row['usual'], 110)
        self.assertEqual(row['spikes'], [0])
        self.assertEqual(row['status'], 'urgent')

    def test_no_usual_sales_sorts_last(self):
        items = [stock('A', quantity=10), stock('B', quantity=200)]
        sold = {**sales('A', 0, 0, 12), **sales('B', 10, 10, 10)}
        rows = build(MONTHS, sold, items, [], set())
        self.assertEqual([(r['article'], r['days']) for r in rows], [('B', 600), ('A', None)])

    def test_small_jump_is_not_a_spike(self):
        row = self.row(stock('A-1'), sales('A-1', 9, 2, 4))
        self.assertEqual(row['spikes'], [])

    def test_production_covers_the_gap(self):
        row = self.row(stock('A-1', quantity=10, in_transit=100), sales('A-1', 50, 50, 50))
        self.assertEqual(row['produce'], 0)
        self.assertEqual(row['status'], 'in_production')

    def test_reserve_on_negative_stock_counts_as_zero(self):
        row = self.row(stock('A-1', quantity=-5), sales('A-1', 4, 4, 4))
        self.assertEqual(row['available'], 0)
        self.assertEqual(row['produce'], 8)

    def test_without_sales_not_in_plan(self):
        self.assertIsNone(self.row(stock('A-1', quantity=10), {}))

    def test_excluded_by_article_or_word(self):
        sold = sales('16-05EX0500', 10, 10, 10)
        self.assertIsNone(self.row(stock('16-05EX0500', 'Декалар'), sold, rules=['16-05 ex0500']))
        self.assertIsNone(self.row(stock('16-05EX0500', 'Уши кролика LuckyPro'), sold, rules=['Уши']))
        self.assertIsNotNone(self.row(stock('16-05EX0500', 'Декалар'), sold, rules=['Мармелад']))

    def test_channels_sum_by_month(self):
        sold = {'A-1': {'ozon': {JUL: 10}, 'wb': {JUL: 5, SEP: 7}}}
        row = self.row(stock('a-1'), sold, green={'A-1'})
        self.assertEqual(row['months'], [15, 0, 7])
        self.assertEqual([c['key'] for c in row['channels']], ['ozon', 'wb'])
        self.assertEqual(row['channels'][1]['months'], [5, 0, 7])
        self.assertTrue(row['green'])

    def test_what_runs_out_sooner_goes_first(self):
        items = [stock('11-11AP0500', 'ХФ+ 500', quantity=296), stock('05-01VP1000', 'Витамин Е', quantity=23)]
        sold = {**sales('11-11AP0500', 176, 345, 259), **sales('05-01VP1000', 56, 19, 71)}
        rows = build(MONTHS, sold, items, [], set())
        self.assertEqual([(r['article'], r['days'], r['status']) for r in rows], [
            ('05-01VP1000', 12, 'urgent'), ('11-11AP0500', 34, 'produce'),
        ])

    def test_urgent_first_then_fewer_days_then_amount(self):
        items = [stock('A', quantity=100), stock('B', quantity=0), stock('C', quantity=0)]
        sold = {**sales('A', 100, 100, 100), **sales('B', 5, 5, 5), **sales('C', 1, 1, 1)}
        self.assertEqual([r['article'] for r in build(MONTHS, sold, items, [], set())], ['B', 'C', 'A'])


class CollectSalesTests(TestCase):
    def ship(self, counterparty, quantity, day=date(2026, 8, 15), article='A-1'):
        product, _ = Product.objects.get_or_create(external_id=article, defaults={'name': article, 'article': article})
        party, _ = Counterparty.objects.get_or_create(name=counterparty, defaults={'external_id': counterparty})
        shipment = Shipment.objects.create(
            counterparty=party, external_id=f'sh-{Shipment.all_objects.count()}',
            date=datetime(day.year, day.month, day.day, 12, tzinfo=dt_timezone.utc),
        )
        ShipmentItem.objects.create(shipment=shipment, product=product, quantity=Decimal(quantity))

    def test_ozon_from_api_and_shipments_by_counterparty(self):
        OzonMonthSales.objects.create(month=AUG, article='A-1', quantity=40)
        self.ship('Озон', 500)
        self.ship('Озон (старый)', 300)
        self.ship('Вб Вайлдберриз', 7)
        self.ship('Яндекс Маркет (ЯМ)', 3)
        self.ship('Озон (ИП Труберг)', 2)
        self.ship('Конный магазин Гандикап', 11)
        self.ship('Конный магазин Гандикап', 99, day=date(2026, 10, 1))
        result = collect_sales(MONTHS)['A-1']
        self.assertEqual({key: dict(value) for key, value in result.items()}, {
            'ozon': {AUG: 40}, 'wb_shipped': {AUG: 7}, 'yandex': {AUG: 3}, 'ozon_ip': {AUG: 2}, 'direct': {AUG: 11},
        })

    def test_wb_falls_back_to_shipments_when_loading_stopped(self):
        WbSync.objects.create(covered_from=JUL)
        WbSync.objects.update(synced_at=datetime(2026, 9, 10, 7, tzinfo=dt_timezone.utc))
        WbOrder.objects.create(srid='s', date=datetime(2026, 9, 3, 9, tzinfo=dt_timezone.utc), article='A-1')
        self.ship('Вб Вайлдберриз', 40, day=date(2026, 9, 12))
        result = collect_sales(MONTHS)['A-1']
        self.assertNotIn(SEP, result['wb'])
        self.assertEqual(dict(result['wb_shipped']), {SEP: 40})

    def test_wb_from_its_orders_only_for_months_fully_loaded(self):
        WbSync.objects.create(covered_from=AUG)
        for i, day in enumerate((datetime(2026, 8, 3, 9), datetime(2026, 8, 20, 9), datetime(2026, 7, 30, 9))):
            WbOrder.objects.create(srid=f's{i}', date=day.replace(tzinfo=dt_timezone.utc), article='A-1')
        WbOrder.objects.create(srid='cancelled', date=datetime(2026, 8, 5, 9, tzinfo=dt_timezone.utc), article='A-1', is_cancel=True)
        self.ship('Вб Вайлдберриз', 500, day=date(2026, 8, 10))
        self.ship('Вб Вайлдберриз', 70, day=date(2026, 7, 10))
        result = collect_sales(MONTHS)['A-1']
        self.assertEqual(dict(result['wb']), {AUG: 2})
        self.assertEqual(dict(result['wb_shipped']), {JUL: 70})
