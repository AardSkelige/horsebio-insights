# forecasting/tests/test_purchase_analyzer.py

from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import (
    Counterparty,
    RawMaterial,
    PurchaseOrder,
    PurchaseOrderItem,
    Supply,
    SupplyItem,
)
from forecasting.services.analysis.optimized_purchase_analyzer import OptimizedPurchaseAnalyzer


class PurchaseAnalyzerTests(TestCase):
    """Tests for OptimizedPurchaseAnalyzer."""

    def setUp(self):
        """Create test data for purchase analysis."""
        # Create suppliers
        self.supplier1 = Counterparty.objects.create(
            name='Supplier Alpha',
            external_id='sup-001'
        )
        self.supplier2 = Counterparty.objects.create(
            name='Supplier Beta',
            external_id='sup-002'
        )

        # Create material
        self.material = RawMaterial.objects.create(
            name='Test Material',
            external_id='mat-001',
            group='Сырье',
            uom_name='кг'
        )

        now = timezone.now()

        # Create purchase orders for supplier1 (3 orders, 2 completed)
        for i in range(3):
            order_date = now - timedelta(days=90 - i * 30)
            order = PurchaseOrder.objects.create(
                counterparty=self.supplier1,
                date=order_date,
                created=order_date,
                external_id=f'po-s1-{i}',
                number=f'PO-S1-{i:04d}',
                sum=Decimal('10000')
            )
            PurchaseOrderItem.objects.create(
                purchase_order=order,
                raw_material=self.material,
                quantity=Decimal('100'),
                price=Decimal('100')
            )

            # Create matching supply for first 2 orders (completed)
            if i < 2:
                supply_date = order_date + timedelta(days=7 + i * 2)  # 7-11 days lead time
                supply = Supply.objects.create(
                    counterparty=self.supplier1,
                    date=supply_date,
                    external_id=f'sup-s1-{i}',
                    number=f'SUP-S1-{i:04d}',
                    sum=Decimal('10000')
                )
                SupplyItem.objects.create(
                    supply=supply,
                    raw_material=self.material,
                    quantity=Decimal('100'),
                    price=Decimal('100'),
                    total=Decimal('10000')
                )

        # Create purchase orders for supplier2 (2 orders, both completed)
        for i in range(2):
            order_date = now - timedelta(days=60 - i * 20)
            order = PurchaseOrder.objects.create(
                counterparty=self.supplier2,
                date=order_date,
                created=order_date,
                external_id=f'po-s2-{i}',
                number=f'PO-S2-{i:04d}',
                sum=Decimal('5000')
            )
            PurchaseOrderItem.objects.create(
                purchase_order=order,
                raw_material=self.material,
                quantity=Decimal('50'),
                price=Decimal('100')
            )

            # Create matching supply (14-18 days lead time - slower supplier)
            supply_date = order_date + timedelta(days=14 + i * 4)
            supply = Supply.objects.create(
                counterparty=self.supplier2,
                date=supply_date,
                external_id=f'sup-s2-{i}',
                number=f'SUP-S2-{i:04d}',
                sum=Decimal('5000')
            )
            SupplyItem.objects.create(
                supply=supply,
                raw_material=self.material,
                quantity=Decimal('50'),
                price=Decimal('100'),
                total=Decimal('5000')
            )

    def test_analyze_supplier_performance(self):
        """Test supplier performance analysis."""
        analyzer = OptimizedPurchaseAnalyzer()
        result = analyzer.analyze_supplier_performance(self.material.id)

        # Should have suppliers data
        self.assertIn('suppliers', result)
        self.assertEqual(len(result['suppliers']), 2)

    def test_supplier_stats_accuracy(self):
        """Test that supplier statistics are calculated correctly."""
        analyzer = OptimizedPurchaseAnalyzer()
        result = analyzer.analyze_supplier_performance(self.material.id)

        suppliers = result['suppliers']

        # Find supplier1 stats
        supplier1_stats = suppliers.get(self.supplier1.id)
        self.assertIsNotNone(supplier1_stats)
        self.assertEqual(supplier1_stats['supplier_name'], 'Supplier Alpha')
        self.assertEqual(supplier1_stats['total_orders'], 3)
        self.assertEqual(supplier1_stats['completed_orders'], 2)

        # Find supplier2 stats
        supplier2_stats = suppliers.get(self.supplier2.id)
        self.assertIsNotNone(supplier2_stats)
        self.assertEqual(supplier2_stats['supplier_name'], 'Supplier Beta')
        self.assertEqual(supplier2_stats['total_orders'], 2)
        self.assertEqual(supplier2_stats['completed_orders'], 2)

    def test_lead_time_calculation(self):
        """Test that lead times are calculated correctly."""
        analyzer = OptimizedPurchaseAnalyzer()
        result = analyzer.analyze_supplier_performance(self.material.id)

        suppliers = result['suppliers']

        # Supplier1: lead times 7 and 9 days -> avg ~8
        supplier1_stats = suppliers.get(self.supplier1.id)
        self.assertGreater(supplier1_stats['avg_lead_time'], 0)
        self.assertLessEqual(supplier1_stats['min_lead_time'], 9)

        # Supplier2: lead times 14 and 18 days -> avg 16
        supplier2_stats = suppliers.get(self.supplier2.id)
        self.assertGreater(supplier2_stats['avg_lead_time'], 10)

    def test_delivery_reliability(self):
        """Test delivery reliability calculation."""
        analyzer = OptimizedPurchaseAnalyzer()
        result = analyzer.analyze_supplier_performance(self.material.id)

        suppliers = result['suppliers']

        # Supplier1: 2/3 completed = 66.7%
        supplier1_stats = suppliers.get(self.supplier1.id)
        self.assertIn('delivery_reliability', supplier1_stats)
        self.assertAlmostEqual(
            supplier1_stats['delivery_reliability'],
            2/3,
            places=2
        )

        # Supplier2: 2/2 completed = 100%
        supplier2_stats = suppliers.get(self.supplier2.id)
        self.assertEqual(supplier2_stats['delivery_reliability'], 1.0)

    def test_no_orders_for_material(self):
        """Test analysis when material has no orders."""
        # Create material with no orders
        empty_material = RawMaterial.objects.create(
            name='Empty Material',
            external_id='mat-empty',
            group='Сырье',
            uom_name='шт'
        )

        analyzer = OptimizedPurchaseAnalyzer()
        result = analyzer.analyze_supplier_performance(empty_material.id)

        self.assertIn('suppliers', result)
        self.assertEqual(len(result['suppliers']), 0)

    def test_nonexistent_material(self):
        """Test analysis for non-existent material."""
        analyzer = OptimizedPurchaseAnalyzer()
        result = analyzer.analyze_supplier_performance(99999)

        self.assertIn('suppliers', result)
        self.assertEqual(len(result['suppliers']), 0)
