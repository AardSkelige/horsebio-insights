"""
Tests for DRF serializers.
"""
from decimal import Decimal
from datetime import date, datetime, timedelta
from django.test import TestCase
from django.utils import timezone

from api.serializers import (
    DecimalFloatField,
    BaseModelSerializer,
    CounterpartySerializer,
    CounterpartyListSerializer,
    ProductSerializer,
    ProductListSerializer,
    RawMaterialSerializer,
    ShipmentSerializer,
    ShipmentListSerializer,
    SupplySerializer,
    SupplyListSerializer,
    DateRangeSerializer,
    PaginationSerializer,
    SortingSerializer,
    SearchFilterSerializer,
    StatisticsSerializer,
    MonthlyDataSerializer,
    ABCCategoryMetricsSerializer,
)
from core.models import Counterparty, Product, RawMaterial, Shipment, Supply


class DecimalFloatFieldTests(TestCase):
    """Tests for DecimalFloatField."""

    def test_to_representation_with_decimal(self):
        """Test that Decimal is converted to float."""
        field = DecimalFloatField(max_digits=10, decimal_places=2)
        result = field.to_representation(Decimal('123.45'))
        self.assertEqual(result, 123.45)
        self.assertIsInstance(result, float)

    def test_to_representation_with_none(self):
        """Test that None returns None."""
        field = DecimalFloatField(max_digits=10, decimal_places=2)
        result = field.to_representation(None)
        self.assertIsNone(result)

    def test_to_representation_with_integer(self):
        """Test that integer Decimal is converted correctly."""
        field = DecimalFloatField(max_digits=10, decimal_places=2)
        result = field.to_representation(Decimal('100'))
        self.assertEqual(result, 100.0)


class BaseModelSerializerTests(TestCase):
    """Tests for BaseModelSerializer helper methods."""

    def setUp(self):
        """Create a concrete serializer for testing."""
        class TestSerializer(BaseModelSerializer):
            class Meta:
                model = Counterparty
                fields = ['id', 'name']

        self.serializer = TestSerializer()

    def test_get_float_value_with_valid_number(self):
        """Test conversion of valid number."""
        result = self.serializer.get_float_value(123.45)
        self.assertEqual(result, 123.45)

    def test_get_float_value_with_none(self):
        """Test that None returns default."""
        result = self.serializer.get_float_value(None)
        self.assertEqual(result, 0.0)

    def test_get_float_value_with_custom_default(self):
        """Test that custom default is used."""
        result = self.serializer.get_float_value(None, default=99.9)
        self.assertEqual(result, 99.9)

    def test_get_float_value_with_decimal(self):
        """Test conversion of Decimal."""
        result = self.serializer.get_float_value(Decimal('456.78'))
        self.assertEqual(result, 456.78)

    def test_get_float_value_with_string_number(self):
        """Test conversion of string number."""
        result = self.serializer.get_float_value('123.45')
        self.assertEqual(result, 123.45)

    def test_get_float_value_with_invalid_string(self):
        """Test that invalid string returns default."""
        result = self.serializer.get_float_value('not a number')
        self.assertEqual(result, 0.0)

    def test_get_float_value_with_nan(self):
        """Test that NaN returns default."""
        result = self.serializer.get_float_value(float('nan'))
        self.assertEqual(result, 0.0)


class CounterpartySerializerTests(TestCase):
    """Tests for Counterparty serializers."""

    def setUp(self):
        """Create test counterparty."""
        self.counterparty = Counterparty.objects.create(
            name='Test Supplier',
            external_id='ext-123',
            is_legacy=False
        )

    def test_serialization(self):
        """Test basic serialization."""
        serializer = CounterpartySerializer(self.counterparty)
        data = serializer.data

        self.assertEqual(data['id'], self.counterparty.id)
        self.assertEqual(data['name'], 'Test Supplier')
        self.assertEqual(data['external_id'], 'ext-123')
        self.assertEqual(data['is_legacy'], False)

    def test_read_only_fields(self):
        """Test that id and external_id are read-only."""
        serializer = CounterpartySerializer(
            self.counterparty,
            data={'id': 999, 'external_id': 'new-ext', 'name': 'Updated Name'}
        )
        self.assertTrue(serializer.is_valid())
        # Read-only fields should not be updated
        self.assertEqual(serializer.validated_data.get('name'), 'Updated Name')
        self.assertNotIn('id', serializer.validated_data)
        self.assertNotIn('external_id', serializer.validated_data)


class ProductSerializerTests(TestCase):
    """Tests for Product serializers."""

    def setUp(self):
        """Create test product."""
        self.product = Product.objects.create(
            name='Test Product',
            external_id='prod-123',
            group='Group A',
            subgroup='Subgroup 1',
            article='ART-001',
            code='CODE-001',
            uom_name='шт'
        )

    def test_serialization(self):
        """Test basic serialization."""
        serializer = ProductSerializer(self.product)
        data = serializer.data

        self.assertEqual(data['name'], 'Test Product')
        self.assertEqual(data['group'], 'Group A')
        self.assertEqual(data['subgroup'], 'Subgroup 1')
        self.assertEqual(data['article'], 'ART-001')
        self.assertEqual(data['uom_name'], 'шт')

    def test_list_serializer_fields(self):
        """Test that list serializer has aggregation fields."""
        serializer = ProductListSerializer(self.product)
        data = serializer.data

        self.assertIn('id', data)
        self.assertIn('name', data)
        self.assertIn('group', data)


class RawMaterialSerializerTests(TestCase):
    """Tests for RawMaterial serializers."""

    def setUp(self):
        """Create test raw material."""
        self.material = RawMaterial.objects.create(
            name='Test Material',
            external_id='mat-123',
            group='Materials Group',
            article='MAT-001',
            code='MATCODE-001',
            uom_name='кг'
        )

    def test_serialization(self):
        """Test basic serialization."""
        serializer = RawMaterialSerializer(self.material)
        data = serializer.data

        self.assertEqual(data['name'], 'Test Material')
        self.assertEqual(data['group'], 'Materials Group')
        self.assertEqual(data['article'], 'MAT-001')
        self.assertEqual(data['uom_name'], 'кг')


class DateRangeSerializerTests(TestCase):
    """Tests for DateRangeSerializer validation."""

    def test_valid_date_range(self):
        """Test valid date range."""
        serializer = DateRangeSerializer(data={
            'start_date': '2024-01-01',
            'end_date': '2024-12-31'
        })
        self.assertTrue(serializer.is_valid())

    def test_invalid_date_range(self):
        """Test that end_date before start_date is invalid."""
        serializer = DateRangeSerializer(data={
            'start_date': '2024-12-31',
            'end_date': '2024-01-01'
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)

    def test_optional_dates(self):
        """Test that dates are optional."""
        serializer = DateRangeSerializer(data={})
        self.assertTrue(serializer.is_valid())

    def test_only_start_date(self):
        """Test with only start_date."""
        serializer = DateRangeSerializer(data={
            'start_date': '2024-01-01'
        })
        self.assertTrue(serializer.is_valid())

    def test_only_end_date(self):
        """Test with only end_date."""
        serializer = DateRangeSerializer(data={
            'end_date': '2024-12-31'
        })
        self.assertTrue(serializer.is_valid())


class PaginationSerializerTests(TestCase):
    """Tests for PaginationSerializer validation."""

    def test_valid_pagination(self):
        """Test valid pagination parameters."""
        serializer = PaginationSerializer(data={
            'page': 1,
            'page_size': 20
        })
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['page'], 1)
        self.assertEqual(serializer.validated_data['page_size'], 20)

    def test_default_values(self):
        """Test default values are applied."""
        serializer = PaginationSerializer(data={})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['page'], 1)
        self.assertEqual(serializer.validated_data['page_size'], 10)

    def test_invalid_page_zero(self):
        """Test that page 0 is invalid."""
        serializer = PaginationSerializer(data={'page': 0})
        self.assertFalse(serializer.is_valid())
        self.assertIn('page', serializer.errors)

    def test_invalid_page_negative(self):
        """Test that negative page is invalid."""
        serializer = PaginationSerializer(data={'page': -1})
        self.assertFalse(serializer.is_valid())

    def test_invalid_page_size_too_large(self):
        """Test that page_size > 500 is invalid."""
        serializer = PaginationSerializer(data={'page_size': 501})
        self.assertFalse(serializer.is_valid())
        self.assertIn('page_size', serializer.errors)

    def test_max_page_size(self):
        """Test that page_size 500 is valid."""
        serializer = PaginationSerializer(data={'page_size': 500})
        self.assertTrue(serializer.is_valid())


class SortingSerializerTests(TestCase):
    """Tests for SortingSerializer validation."""

    def test_valid_sorting(self):
        """Test valid sorting parameters."""
        serializer = SortingSerializer(data={
            'sort_field': 'date',
            'sort_order': 'asc'
        })
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['sort_field'], 'date')
        self.assertEqual(serializer.validated_data['sort_order'], 'asc')

    def test_default_values(self):
        """Test default values are applied."""
        serializer = SortingSerializer(data={})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['sort_field'], 'name')
        self.assertEqual(serializer.validated_data['sort_order'], 'desc')

    def test_invalid_sort_order(self):
        """Test that invalid sort_order is rejected."""
        serializer = SortingSerializer(data={'sort_order': 'invalid'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('sort_order', serializer.errors)


class SearchFilterSerializerTests(TestCase):
    """Tests for SearchFilterSerializer validation."""

    def test_valid_search(self):
        """Test valid search parameters."""
        serializer = SearchFilterSerializer(data={
            'search': 'test query',
            'group': 'Group A'
        })
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['search'], 'test query')
        self.assertEqual(serializer.validated_data['group'], 'Group A')

    def test_default_values(self):
        """Test default values are applied."""
        serializer = SearchFilterSerializer(data={})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['search'], '')
        self.assertEqual(serializer.validated_data['group'], '')

    def test_empty_strings_allowed(self):
        """Test that empty strings are allowed."""
        serializer = SearchFilterSerializer(data={
            'search': '',
            'group': ''
        })
        self.assertTrue(serializer.is_valid())


class StatisticsSerializerTests(TestCase):
    """Tests for StatisticsSerializer."""

    def test_valid_statistics(self):
        """Test valid statistics data."""
        data = {
            'shipments_count': 100,
            'shipments_current_month': 10,
            'supplies_count': 50,
            'supplies_current_month': 5,
            'last_manual_update': '2024-01-15 10:00:00',
            'last_auto_update': '2024-01-15 12:00:00',
            'latest_update_type': 'auto',
            'latest_update_time': '2024-01-15 12:00:00'
        }
        serializer = StatisticsSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_null_update_fields(self):
        """Test that update fields can be null."""
        data = {
            'shipments_count': 100,
            'shipments_current_month': 10,
            'supplies_count': 50,
            'supplies_current_month': 5,
            'last_manual_update': None,
            'last_auto_update': None,
            'latest_update_type': None,
            'latest_update_time': None
        }
        serializer = StatisticsSerializer(data=data)
        self.assertTrue(serializer.is_valid())


class MonthlyDataSerializerTests(TestCase):
    """Tests for MonthlyDataSerializer."""

    def test_valid_monthly_data(self):
        """Test valid monthly data."""
        data = {
            'month': 'Январь',
            'year': 2024,
            'shipments': 25,
            'supplies': 15
        }
        serializer = MonthlyDataSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_missing_required_field(self):
        """Test that missing required fields cause error."""
        data = {
            'month': 'Январь',
            'year': 2024
        }
        serializer = MonthlyDataSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('shipments', serializer.errors)


class ABCCategoryMetricsSerializerTests(TestCase):
    """Tests for ABCCategoryMetricsSerializer."""

    def test_valid_abc_metrics(self):
        """Test valid ABC category metrics."""
        data = {
            'product_count': 10,
            'revenue': '125000.50',
            'revenue_share': '0.7500',
            'quantity': '1500.00',
            'avg_monthly_revenue': '10416.71',
            'avg_monthly_quantity': '125.00'
        }
        serializer = ABCCategoryMetricsSerializer(data=data)
        self.assertTrue(serializer.is_valid())
