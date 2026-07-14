"""
Tests for API views.
"""
import json
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import (
    Counterparty,
    Product,
    RawMaterial,
    Shipment,
    ShipmentItem,
    Supply,
    SupplyItem,
)


class BaseViewTestCase(TestCase):
    """Base test case with common setup for view tests."""

    def setUp(self):
        """Set up test client and authenticate."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')


class StatsViewTests(BaseViewTestCase):
    """Tests for statistics views."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        # Create test counterparty
        self.counterparty = Counterparty.objects.create(
            name='Test Customer',
            external_id='cust-001'
        )
        # Create test product
        self.product = Product.objects.create(
            name='Test Product',
            external_id='prod-001',
            group='Ветпрепараты'
        )
        # Create test shipments with timezone-aware dates
        now = timezone.now()
        for i in range(5):
            shipment = Shipment.objects.create(
                counterparty=self.counterparty,
                date=now - timedelta(days=i),
                external_id=f'ship-{i}',
                number=f'SHP-{i:04d}'
            )
            ShipmentItem.objects.create(
                shipment=shipment,
                product=self.product,
                quantity=Decimal('10'),
                price=Decimal('100')
            )

    def test_general_stats_endpoint(self):
        """Test /api/stats/ endpoint."""
        response = self.client.get('/api/stats/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        # Stats returns 'stats' key not 'data'
        self.assertIn('stats', data)
        self.assertIn('shipments_count', data['stats'])
        self.assertIn('supplies_count', data['stats'])


class ShipmentsViewTests(BaseViewTestCase):
    """Tests for shipments views."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.counterparty = Counterparty.objects.create(
            name='Test Customer',
            external_id='cust-001'
        )
        self.product = Product.objects.create(
            name='Test Product',
            external_id='prod-001',
            group='Ветпрепараты'
        )
        self.shipment = Shipment.objects.create(
            counterparty=self.counterparty,
            date=timezone.now(),
            external_id='ship-001',
            number='SHP-0001'
        )
        self.shipment_item = ShipmentItem.objects.create(
            shipment=self.shipment,
            product=self.product,
            quantity=Decimal('10'),
            price=Decimal('100')
        )

    def test_shipments_endpoint(self):
        """Test /api/shipments/ endpoint."""
        response = self.client.get('/api/shipments/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)

    def test_shipments_with_pagination(self):
        """Test shipments with pagination parameters."""
        response = self.client.get('/api/shipments/?page=1&page_size=10')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_shipments_with_search(self):
        """Test shipments with search parameter."""
        response = self.client.get('/api/shipments/?search=Test')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')


class CounterpartiesViewTests(BaseViewTestCase):
    """Tests for counterparties views."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.counterparty1 = Counterparty.objects.create(
            name='Alpha Customer',
            external_id='cust-001',
            is_legacy=False
        )
        self.counterparty2 = Counterparty.objects.create(
            name='Beta Supplier',
            external_id='cust-002',
            is_legacy=False
        )
        self.product = Product.objects.create(
            name='Test Product',
            external_id='prod-001',
            group='Ветпрепараты'
        )
        # Create shipment for counterparty1 with timezone-aware date
        shipment = Shipment.objects.create(
            counterparty=self.counterparty1,
            date=timezone.now(),
            external_id='ship-001',
            number='SHP-0001'
        )
        ShipmentItem.objects.create(
            shipment=shipment,
            product=self.product,
            quantity=Decimal('10'),
            price=Decimal('100')
        )

    def test_counterparties_list_endpoint(self):
        """Test /api/counterparties/ endpoint."""
        response = self.client.get('/api/counterparties/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)
        self.assertIn('counterparties', data['data'])

    def test_counterparties_list_with_search(self):
        """Test counterparties list with search parameter."""
        response = self.client.get('/api/counterparties/?search=Alpha')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_counterparties_list_sorted(self):
        """Test counterparties list with sorting."""
        response = self.client.get('/api/counterparties/?sort_field=name&sort_order=asc')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')


class ProductsViewTests(BaseViewTestCase):
    """Tests for products views."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.product1 = Product.objects.create(
            name='Product A',
            external_id='prod-001',
            group='Ветпрепараты',
            subgroup='Антибиотики',
            article='ART-001'
        )
        self.product2 = Product.objects.create(
            name='Product B',
            external_id='prod-002',
            group='Кормовые добавки',
            article='ART-002'
        )
        self.counterparty = Counterparty.objects.create(
            name='Test Customer',
            external_id='cust-001'
        )
        # Create shipments for products
        shipment = Shipment.objects.create(
            counterparty=self.counterparty,
            date=date.today(),
            external_id='ship-001',
            number='SHP-0001'
        )
        ShipmentItem.objects.create(
            shipment=shipment,
            product=self.product1,
            quantity=Decimal('10'),
            price=Decimal('100')
        )

    def test_products_list_endpoint(self):
        """Test /api/products/ endpoint."""
        response = self.client.get('/api/products/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)

    def test_products_list_with_group_filter(self):
        """Test products list with group filter."""
        response = self.client.get('/api/products/?group=Ветпрепараты')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_products_list_with_search(self):
        """Test products list with search parameter."""
        response = self.client.get('/api/products/?search=Product A')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')


class MaterialsViewTests(BaseViewTestCase):
    """Tests for materials views."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.material = RawMaterial.objects.create(
            name='Test Material',
            external_id='mat-001',
            group='Сырье',
            article='MAT-001',
            uom_name='кг'
        )

    def test_materials_list_endpoint(self):
        """Test /api/materials/ endpoint."""
        response = self.client.get('/api/materials/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)


class SuppliesViewTests(BaseViewTestCase):
    """Tests for supplies views."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.supplier = Counterparty.objects.create(
            name='Test Supplier',
            external_id='sup-001'
        )
        self.material = RawMaterial.objects.create(
            name='Test Material',
            external_id='mat-001',
            group='Сырье для производства Ветпрепаратов',
            uom_name='кг'
        )
        self.supply = Supply.objects.create(
            counterparty=self.supplier,
            date=timezone.now(),
            external_id='supply-001',
            number='SUP-0001',
            sum=Decimal('10000')
        )
        SupplyItem.objects.create(
            supply=self.supply,
            raw_material=self.material,
            quantity=Decimal('100'),
            price=Decimal('100'),
            total=Decimal('10000')
        )

    def test_supplies_list_endpoint(self):
        """Test /api/supplies/ endpoint."""
        response = self.client.get('/api/supplies/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertIn('data', data)

    def test_supplies_with_date_filter(self):
        """Test supplies with date filter."""
        today = date.today().isoformat()
        response = self.client.get(f'/api/supplies/?start_date={today}&end_date={today}')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')


class ErrorHandlingViewTests(BaseViewTestCase):
    """Tests for error handling in views."""

    def test_unauthenticated_request(self):
        """Test that unauthenticated requests are handled properly."""
        self.client.logout()
        response = self.client.get('/api/stats/')
        # Should handle auth error gracefully
        self.assertIn(response.status_code, [200, 401, 403])

    def test_invalid_pagination_params(self):
        """Test handling of invalid pagination parameters."""
        response = self.client.get('/api/shipments/?page=invalid')
        # Should handle invalid params gracefully (converts to default)
        self.assertIn(response.status_code, [200, 400])

    def test_404_for_nonexistent_endpoint(self):
        """Test that nonexistent endpoints return 404."""
        response = self.client.get('/api/nonexistent/')
        self.assertEqual(response.status_code, 404)
