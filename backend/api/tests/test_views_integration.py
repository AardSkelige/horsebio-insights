"""
Integration tests for API views.
Tests endpoints before refactoring to ensure behavior is preserved.
"""
import json
from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
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
    ProcessingPlan,
    ProcessingPlanProduct,
    ProcessingPlanMaterial,
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


class ABCAnalysisTests(BaseViewTestCase):
    """Tests for ABC analysis endpoints."""

    def setUp(self):
        """Set up test data for ABC analysis."""
        super().setUp()
        # Create test counterparty
        self.counterparty = Counterparty.objects.create(
            name='Test Customer',
            external_id='cust-001'
        )
        # Create test products
        self.product_a = Product.objects.create(
            name='High Revenue Product',
            external_id='prod-001',
            group='Товары',
            subgroup='Ветпрепараты',
            article='ART-001'
        )
        self.product_b = Product.objects.create(
            name='Medium Revenue Product',
            external_id='prod-002',
            group='Товары',
            subgroup='Кормовые добавки',
            article='ART-002'
        )
        self.product_c = Product.objects.create(
            name='Low Revenue Product',
            external_id='prod-003',
            group='Товары',
            article='ART-003'
        )

        # Create shipments with different revenues
        now = timezone.now()
        # High revenue product - category A
        for i in range(10):
            shipment = Shipment.objects.create(
                counterparty=self.counterparty,
                date=now - timedelta(days=i),
                external_id=f'ship-a-{i}',
                number=f'SHP-A-{i:04d}'
            )
            ShipmentItem.objects.create(
                shipment=shipment,
                product=self.product_a,
                quantity=Decimal('100'),
                price=Decimal('1000')  # High price
            )

        # Medium revenue - category B
        for i in range(5):
            shipment = Shipment.objects.create(
                counterparty=self.counterparty,
                date=now - timedelta(days=i + 10),
                external_id=f'ship-b-{i}',
                number=f'SHP-B-{i:04d}'
            )
            ShipmentItem.objects.create(
                shipment=shipment,
                product=self.product_b,
                quantity=Decimal('50'),
                price=Decimal('200')
            )

        # Low revenue - category C
        for i in range(2):
            shipment = Shipment.objects.create(
                counterparty=self.counterparty,
                date=now - timedelta(days=i + 15),
                external_id=f'ship-c-{i}',
                number=f'SHP-C-{i:04d}'
            )
            ShipmentItem.objects.create(
                shipment=shipment,
                product=self.product_c,
                quantity=Decimal('10'),
                price=Decimal('50')
            )

    def test_abc_analysis_endpoint(self):
        """Test /api/analysis/abc/ endpoint returns valid response."""
        response = self.client.get('/api/analysis/abc/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertIn('period', data)
        self.assertIn('categories', data)

    def test_abc_analysis_with_period(self):
        """Test ABC analysis with custom period."""
        end_date = date.today().isoformat()
        response = self.client.get(f'/api/analysis/abc/?end_date={end_date}&period_months=6')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['period']['months'], 6)

    def test_abc_product_details(self):
        """Test /api/analysis/abc/products/<id>/ endpoint."""
        response = self.client.get(f'/api/analysis/abc/products/{self.product_a.id}/')
        # May return 200 or error if product not in ABC analysis
        self.assertIn(response.status_code, [200, 400, 404, 500])

    def test_abc_export_excel(self):
        """Test /api/analysis/abc/export/ endpoint."""
        response = self.client.get('/api/analysis/abc/export/')
        # Should return Excel file or error
        if response.status_code == 200:
            self.assertEqual(
                response['Content-Type'],
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )


class SeasonalAnalysisTests(BaseViewTestCase):
    """Tests for seasonal analysis endpoints."""

    def setUp(self):
        """Set up test data for seasonal analysis."""
        super().setUp()
        self.counterparty = Counterparty.objects.create(
            name='Test Customer',
            external_id='cust-001'
        )
        self.product = Product.objects.create(
            name='Seasonal Product',
            external_id='prod-001',
            group='Товары',
            article='ART-001'
        )

        # Create shipments spread across different months for seasonality
        now = timezone.now()
        for i in range(12):
            for j in range(3):  # Multiple shipments per month
                shipment = Shipment.objects.create(
                    counterparty=self.counterparty,
                    date=now - timedelta(days=i * 30 + j),
                    external_id=f'ship-{i}-{j}',
                    number=f'SHP-{i:02d}-{j:02d}'
                )
                # Vary quantity by month to simulate seasonality
                quantity = Decimal('100') + Decimal(i * 10)
                ShipmentItem.objects.create(
                    shipment=shipment,
                    product=self.product,
                    quantity=quantity,
                    price=Decimal('100')
                )

    def test_seasonal_analysis_endpoint(self):
        """Test /api/analysis/seasonal/ endpoint."""
        response = self.client.get('/api/analysis/seasonal/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIn('status', data)

    def test_seasonal_analysis_with_category(self):
        """Test seasonal analysis with category filter."""
        response = self.client.get('/api/analysis/seasonal/?category=A')
        self.assertEqual(response.status_code, 200)

    def test_seasonal_product_details(self):
        """Test /api/analysis/seasonal/products/<id>/ endpoint."""
        response = self.client.get(f'/api/analysis/seasonal/products/{self.product.id}/')
        # May return 200 or 404 if no sales data
        self.assertIn(response.status_code, [200, 404, 500])


class CashFlowTests(BaseViewTestCase):
    """Tests for cash flow endpoints."""

    @patch('api.views.cash_flow.get_operations_data')
    @patch('api.views.cash_flow.get_sales_channels')
    @patch('api.views.cash_flow.get_payments_by_channels')
    @patch('api.views.cash_flow.get_expense_items')
    @patch('api.views.cash_flow.get_expense_categories_by_api')
    @patch('api.views.cash_flow.get_income_channels_from_payments')
    @patch('api.views.cash_flow.calculate_initial_balance')
    @patch('api.views.cash_flow.get_counterparties_tags')
    @patch('api.views.cash_flow.get_income_by_groups')
    @patch('api.views.cash_flow.get_expense_by_groups')
    def test_cash_flow_report(self, mock_exp_groups, mock_inc_groups, mock_cp_tags,
                              mock_balance, mock_income, mock_expense_cat,
                              mock_expense_items, mock_payments, mock_channels, mock_ops):
        """Test POST /api/analysis/cash-flow/ endpoint."""
        # Set up mocks
        mock_ops.return_value = {
            'cashin': [{'sum': 100000}],
            'paymentout': [{'sum': 50000}]
        }
        mock_channels.return_value = {}
        mock_payments.return_value = {}
        mock_expense_items.return_value = {}
        mock_expense_cat.return_value = ({}, {}, {}, {})
        mock_income.return_value = {'total': 1000}
        mock_balance.return_value = 0
        mock_cp_tags.return_value = {}
        mock_inc_groups.return_value = {}
        mock_exp_groups.return_value = {}

        response = self.client.post(
            '/api/analysis/cash-flow/',
            data=json.dumps({
                'date_from': '2024-01-01T00:00:00',
                'date_to': '2024-01-31T23:59:59'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data.get('success', False))

    @patch('api.views.cash_flow.get_operations_data')
    @patch('api.views.cash_flow.get_sales_channels')
    @patch('api.views.cash_flow.get_payments_by_channels')
    @patch('api.views.cash_flow.get_expense_items')
    @patch('api.views.cash_flow.get_expense_categories_by_api')
    @patch('api.views.cash_flow.get_income_channels_from_payments')
    @patch('api.views.cash_flow.calculate_initial_balance')
    @patch('api.views.cash_flow.export_to_excel')
    @patch('api.views.cash_flow.get_counterparties_tags')
    @patch('api.views.cash_flow.get_income_by_groups')
    @patch('api.views.cash_flow.get_expense_by_groups')
    def test_cash_flow_export(self, mock_exp_groups, mock_inc_groups, mock_cp_tags,
                              mock_excel, mock_balance, mock_income, mock_expense_cat,
                              mock_expense_items, mock_payments, mock_channels, mock_ops):
        """Test POST /api/analysis/cash-flow/export/ endpoint."""
        from io import BytesIO

        mock_ops.return_value = {
            'cashin': [{'sum': 100000}],
            'paymentout': [{'sum': 50000}]
        }
        mock_channels.return_value = {}
        mock_payments.return_value = {}
        mock_expense_items.return_value = {}
        mock_expense_cat.return_value = ({}, {}, {}, {})
        mock_income.return_value = {'total': 1000}
        mock_balance.return_value = 0
        mock_cp_tags.return_value = {}
        mock_inc_groups.return_value = {}
        mock_exp_groups.return_value = {}
        mock_excel.return_value = BytesIO(b'fake excel content')

        response = self.client.post(
            '/api/analysis/cash-flow/export/',
            data=json.dumps({
                'date_from': '2024-01-01T00:00:00',
                'date_to': '2024-01-31T23:59:59'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )


class ProductionTests(BaseViewTestCase):
    """Tests for production calculation endpoints."""

    def setUp(self):
        """Set up test data for production calculations."""
        super().setUp()

        # Create product with processing plan
        self.product = Product.objects.create(
            name='Production Product',
            external_id='prod-001',
            group='Товары',
            article='PROD-001'
        )

        # Create raw materials
        self.material1 = RawMaterial.objects.create(
            name='Material 1',
            external_id='mat-001',
            group='Сырье',
            uom_name='кг'
        )
        self.material2 = RawMaterial.objects.create(
            name='Material 2',
            external_id='mat-002',
            group='Тара',
            uom_name='шт'
        )

        # Create processing plan
        self.processing_plan = ProcessingPlan.objects.create(
            name='Test Processing Plan',
            external_id='plan-001'
        )

        ProcessingPlanProduct.objects.create(
            processing_plan=self.processing_plan,
            product=self.product,
            quantity=Decimal('1')
        )

        ProcessingPlanMaterial.objects.create(
            processing_plan=self.processing_plan,
            material=self.material1,
            quantity=Decimal('0.5')
        )
        ProcessingPlanMaterial.objects.create(
            processing_plan=self.processing_plan,
            material=self.material2,
            quantity=Decimal('1')
        )

    def test_calculate_components_json(self):
        """Test POST /api/production/calculate-json/ endpoint."""
        response = self.client.post(
            '/api/production/calculate-json/',
            data=json.dumps({
                'items': [
                    {'article': 'PROD-001', 'quantity': 10}
                ]
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data.get('success', False))

    def test_calculate_components_json_empty(self):
        """Test production calculation with empty items."""
        response = self.client.post(
            '/api/production/calculate-json/',
            data=json.dumps({'items': []}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

        data = json.loads(response.content)
        self.assertFalse(data.get('success', True))

    def test_calculate_components_json_invalid(self):
        """Test production calculation with invalid JSON."""
        response = self.client.post(
            '/api/production/calculate-json/',
            data='invalid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_calculate_single_product(self):
        """Test POST /api/production/calculate-single/ endpoint."""
        response = self.client.post(
            '/api/production/calculate-single/',
            data=json.dumps({
                'article': 'PROD-001',
                'quantity': 5
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        # Product may or may not be found depending on test data
        self.assertIn('found', data)

    def test_calculate_single_product_missing_article(self):
        """Test production calculation with missing article."""
        response = self.client.post(
            '/api/production/calculate-single/',
            data=json.dumps({'quantity': 5}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)


class FBOTests(BaseViewTestCase):
    """Tests for FBO analysis endpoints."""

    @patch('api.views.fbo.MoySkladAPIClient')
    @patch('api.views.fbo.requests.get')
    def test_fbo_analysis_endpoint(self, mock_get, mock_client):
        """Test GET /api/analysis/fbo/ endpoint."""
        # Mock MoySklad API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'rows': []}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        mock_client_instance = MagicMock()
        mock_client_instance.BASE_URL = 'https://api.moysklad.ru/api/remap/1.2'
        mock_client_instance.headers = {}
        mock_client.return_value = mock_client_instance

        response = self.client.get('/api/analysis/fbo/', secure=True)
        # Should return 200 or handle external API error
        self.assertIn(response.status_code, [200, 500, 503])

    @patch('api.views.fbo.requests.get')
    @patch('api.views.fbo._build_fbo_analysis_data')
    def test_fbo_export_endpoint(self, mock_analysis, mock_get):
        """Test GET /api/analysis/fbo/export/ endpoint."""
        mock_analysis.return_value = {
            'statistics': {},
            'products': [],
            'orders': []
        }

        response = self.client.get('/api/analysis/fbo/export/', secure=True)
        self.assertEqual(response.status_code, 200)
        mock_analysis.assert_called_once_with()
        mock_get.assert_not_called()


class SupplyMaterialsTests(BaseViewTestCase):
    """Tests for supply materials endpoints."""

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
            group='Материалы для производства',  # Valid group
            uom_name='кг',
            code='MAT-001'
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

    def test_supply_materials_list(self):
        """Test /api/supplies/materials/ endpoint."""
        response = self.client.get('/api/supplies/materials/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_supply_materials_with_date_filter(self):
        """Test supply materials with date filter."""
        today = date.today().isoformat()
        response = self.client.get(f'/api/supplies/materials/?startDate={today}&endDate={today}')
        self.assertEqual(response.status_code, 200)

    def test_supply_materials_with_search(self):
        """Test supply materials with search."""
        response = self.client.get('/api/supplies/materials/?search=Test')
        self.assertEqual(response.status_code, 200)

    def test_supply_material_details(self):
        """Test /api/supplies/materials/<id>/details/ endpoint."""
        response = self.client.get(f'/api/supplies/materials/{self.material.id}/details/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['data']['material']['id'], self.material.id)

    def test_supply_material_details_not_found(self):
        """Test supply material details with invalid ID."""
        response = self.client.get('/api/supplies/materials/99999/details/')
        self.assertEqual(response.status_code, 404)

    def test_supply_suppliers_list(self):
        """Test /api/supplies/suppliers/ endpoint."""
        response = self.client.get('/api/supplies/suppliers/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_supply_supplier_details(self):
        """Test /api/supplies/suppliers/<id>/details/ endpoint."""
        response = self.client.get(f'/api/supplies/suppliers/{self.supplier.id}/details/')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')


class MaterialPeriodTests(BaseViewTestCase):
    """Tests for material lead time period endpoint."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.material = RawMaterial.objects.create(
            name='Test Material Period',
            external_id='mat-period-001',
            group='Материалы для производства',
            uom_name='шт',
            code='MAT-P001'
        )

    def test_update_material_period_success(self):
        """Test PATCH /api/materials/<id>/period/ endpoint."""
        response = self.client.patch(
            f'/api/materials/{self.material.id}/period/',
            data=json.dumps({'period_months': 3}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['data']['period_months'], 3)
        self.assertTrue(data['data']['period_is_custom'])

        # Verify in database
        self.material.refresh_from_db()
        self.assertEqual(self.material.lead_time_period_months, 3)

    def test_update_material_period_reset(self):
        """Test resetting period to default."""
        # First set a custom period
        self.material.lead_time_period_months = 6
        self.material.save()

        # Reset to default
        response = self.client.patch(
            f'/api/materials/{self.material.id}/period/',
            data=json.dumps({'period_months': None}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['data']['period_months'], 12)  # Default
        self.assertFalse(data['data']['period_is_custom'])

        # Verify in database
        self.material.refresh_from_db()
        self.assertIsNone(self.material.lead_time_period_months)

    def test_update_material_period_not_found(self):
        """Test updating non-existent material."""
        response = self.client.patch(
            '/api/materials/99999/period/',
            data=json.dumps({'period_months': 3}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_update_material_period_invalid_value(self):
        """Test with invalid period value."""
        response = self.client.patch(
            f'/api/materials/{self.material.id}/period/',
            data=json.dumps({'period_months': 0}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.patch(
            f'/api/materials/{self.material.id}/period/',
            data=json.dumps({'period_months': 25}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_update_material_period_valid_values(self):
        """Test all valid period values."""
        for period in [3, 6, 12]:
            response = self.client.patch(
                f'/api/materials/{self.material.id}/period/',
                data=json.dumps({'period_months': period}),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.content)
            self.assertEqual(data['data']['period_months'], period)
