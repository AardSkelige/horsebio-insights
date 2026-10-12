from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from core.models import Counterparty, Product, RawMaterial, RawMaterialUsage, Shipment, ShipmentItem
from forecasting.services.analysis.purchase_optimizer import (
    OrderHistory,
    PurchaseOptimizationCalculator,
)


class PurchaseOptimizationCalculatorTests(TestCase):
    def setUp(self):
        self.material = RawMaterial.objects.create(
            name='Масло льняное', external_id='mat-oil', uom_name='мл'
        )
        self.orders = [
            OrderHistory(quantity=1_500_000, lead_time=lt, date='2026-01-01', price=0.2, supplier_name='Экофа')
            for lt in (10, 24, 8, 41)
        ]

    def make_calculator(self, daily):
        with mock.patch.object(
            PurchaseOptimizationCalculator,
            'calculate_total_material_consumption',
            return_value={'value': daily, 'details': ''},
        ):
            return PurchaseOptimizationCalculator(self.orders, self.material.id)

    def test_working_week_is_monday_to_friday(self):
        calc = self.make_calculator(100)
        self.assertEqual(calc._calculate_working_days(date(2026, 10, 12), date(2026, 10, 18)), 5)

    def test_holidays_and_transferred_days_off_are_not_working_days(self):
        calc = self.make_calculator(100)
        self.assertEqual(calc._calculate_working_days(date(2026, 1, 1), date(2026, 1, 11)), 0)
        self.assertEqual(calc._calculate_working_days(date(2026, 1, 1), date(2026, 12, 31)), 247)
        self.assertEqual(calc._calculate_working_days(date(2025, 5, 1), date(2025, 5, 2)), 0)

    def test_monthly_order_is_consumption_over_working_days_without_safety_stock(self):
        calc = self.make_calculator(100)
        orders = calc.calculate_periodic_orders()

        monthly = orders['frequent_orders']['order_size']
        self.assertAlmostEqual(monthly, 100 * calc.working_days_per_year / 12)
        self.assertAlmostEqual(orders['quarterly_orders']['order_size'], monthly * 3)

    def test_reorder_point_does_not_include_past_order_size(self):
        calc = self.make_calculator(100)
        lead = calc.calculate_lead_time_stats()
        calendar_daily = 100 * calc.working_days_per_year / calc.calendar_days_per_year

        reorder_point = calc.calculate_reorder_point()['value']

        self.assertAlmostEqual(reorder_point, calendar_daily * (lead['avg'] + lead['stddev']))
        self.assertLess(reorder_point, 1_500_000)

    def test_safety_stock_is_at_least_a_week_of_consumption(self):
        self.orders = self.orders[:1]
        calc = self.make_calculator(100)
        calendar_daily = 100 * calc.working_days_per_year / calc.calendar_days_per_year

        reorder_point = calc.calculate_reorder_point()['value']

        self.assertAlmostEqual(reorder_point, calendar_daily * 10 + 100 * 5)

    def test_lead_time_stats_report_min_and_max(self):
        lead = self.make_calculator(100).calculate_lead_time_stats()
        self.assertEqual((lead['min'], lead['max']), (8, 41))

    def test_orders_without_supply_do_not_shorten_lead_time(self):
        self.orders.append(
            OrderHistory(quantity=1_500_000, lead_time=None, date='2026-10-01', price=0.2, supplier_name='Экофа')
        )
        lead = self.make_calculator(100).calculate_lead_time_stats()
        self.assertEqual((lead['avg'], lead['min']), (20.75, 8))

    def test_fallback_without_usage_is_per_working_day(self):
        self.orders = [
            OrderHistory(quantity=500, lead_time=5, date='2026-10-12T00:00:00', price=1),
            OrderHistory(quantity=500, lead_time=5, date='2026-10-16T00:00:00', price=1),
        ]
        calc = PurchaseOptimizationCalculator(self.orders, self.material.id)
        self.assertAlmostEqual(calc.total_consumption['value'], 200)

    def test_consumption_uses_selected_period(self):
        counterparty = Counterparty.objects.create(external_id='agent', name='Покупатель')
        product = Product.objects.create(external_id='product', name='Эликсир')
        for days_ago, quantity in ((20, 100), (200, 900)):
            shipment = Shipment.objects.create(
                external_id=f'shipment-{days_ago}',
                date=timezone.now() - timedelta(days=days_ago),
                counterparty=counterparty,
            )
            item = ShipmentItem.objects.create(shipment=shipment, product=product, quantity=1, price=1)
            RawMaterialUsage.objects.create(shipment_item=item, raw_material=self.material, quantity=Decimal(quantity))

        three = PurchaseOptimizationCalculator(self.orders, self.material.id, consumption_months=3)
        twelve = PurchaseOptimizationCalculator(self.orders, self.material.id, consumption_months=12)

        self.assertEqual(three.total_consumption['total_quantity'], 100)
        self.assertEqual(twelve.total_consumption['total_quantity'], 1000)
        self.assertLess(three.total_consumption['value'], 100)
