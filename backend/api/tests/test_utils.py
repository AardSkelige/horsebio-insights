"""
Tests for API utility functions.
"""
from decimal import Decimal
from datetime import datetime
from io import BytesIO

from django.test import TestCase
from django.utils import timezone

from api.utils import (
    parse_date_param,
    apply_date_filter,
    get_period_dates,
    to_float_safe,
    format_decimal_fields,
    create_excel_response,
    ExcelReportBuilder,
)


class DateHelpersTests(TestCase):
    """Tests for date helper functions."""

    def test_parse_date_param_valid(self):
        """Test parsing valid date string."""
        result = parse_date_param('2024-01-15')
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.hour, 0)
        self.assertEqual(result.minute, 0)
        self.assertTrue(timezone.is_aware(result))

    def test_parse_date_param_end_of_day(self):
        """Test parsing date with end_of_day flag."""
        result = parse_date_param('2024-01-15', end_of_day=True)
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 23)
        self.assertEqual(result.minute, 59)
        self.assertEqual(result.second, 59)

    def test_parse_date_param_invalid(self):
        """Test parsing invalid date string."""
        result = parse_date_param('invalid-date')
        self.assertIsNone(result)

    def test_parse_date_param_none(self):
        """Test parsing None value."""
        result = parse_date_param(None)
        self.assertIsNone(result)

    def test_parse_date_param_empty(self):
        """Test parsing empty string."""
        result = parse_date_param('')
        self.assertIsNone(result)

    def test_parse_date_param_custom_format(self):
        """Test parsing date with custom format."""
        result = parse_date_param('15/01/2024', date_format='%d/%m/%Y')
        self.assertIsNotNone(result)
        self.assertEqual(result.day, 15)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.year, 2024)

    def test_get_period_dates_with_end_date(self):
        """Test get_period_dates with explicit end date."""
        start, end = get_period_dates('2024-06-30', period_months=6)
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        # End should be June 30, 2024
        self.assertEqual(end.month, 6)
        self.assertEqual(end.day, 30)
        # Start should be approximately 6 months before
        self.assertTrue((end - start).days >= 175)  # ~6 months

    def test_get_period_dates_without_end_date(self):
        """Test get_period_dates without end date (uses current date)."""
        start, end = get_period_dates(None, period_months=12)
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        # Should be approximately 360 days difference
        self.assertTrue((end - start).days >= 350)


class ApplyDateFilterTests(TestCase):
    """Tests for apply_date_filter function."""

    def setUp(self):
        """Set up test data."""
        from core.models import Counterparty, Supply
        self.supplier = Counterparty.objects.create(
            name='Test Supplier',
            external_id='sup-001'
        )
        # Create supplies on different dates
        dates = ['2024-01-15', '2024-02-15', '2024-03-15']
        for i, date_str in enumerate(dates):
            Supply.objects.create(
                counterparty=self.supplier,
                date=timezone.make_aware(
                    datetime.strptime(date_str, '%Y-%m-%d')
                ),
                external_id=f'supply-{i}',
                number=f'SUP-{i:04d}',
                sum=Decimal('1000')
            )

    def test_apply_date_filter_start_only(self):
        """Test filtering with start date only."""
        from core.models import Supply
        qs = Supply.objects.all()
        filtered = apply_date_filter(qs, '2024-02-01', None)
        self.assertEqual(filtered.count(), 2)  # Feb and March

    def test_apply_date_filter_end_only(self):
        """Test filtering with end date only."""
        from core.models import Supply
        qs = Supply.objects.all()
        filtered = apply_date_filter(qs, None, '2024-02-28')
        self.assertEqual(filtered.count(), 2)  # Jan and Feb

    def test_apply_date_filter_both_dates(self):
        """Test filtering with both dates."""
        from core.models import Supply
        qs = Supply.objects.all()
        filtered = apply_date_filter(qs, '2024-02-01', '2024-02-28')
        self.assertEqual(filtered.count(), 1)  # Only Feb

    def test_apply_date_filter_no_dates(self):
        """Test filtering without dates returns all."""
        from core.models import Supply
        qs = Supply.objects.all()
        filtered = apply_date_filter(qs, None, None)
        self.assertEqual(filtered.count(), 3)

    def test_apply_date_filter_invalid_dates(self):
        """Test filtering with invalid dates returns all."""
        from core.models import Supply
        qs = Supply.objects.all()
        filtered = apply_date_filter(qs, 'invalid', 'also-invalid')
        self.assertEqual(filtered.count(), 3)


class ResponseHelpersTests(TestCase):
    """Tests for response helper functions."""

    def test_to_float_safe_normal(self):
        """Test converting normal values."""
        self.assertEqual(to_float_safe(10), 10.0)
        self.assertEqual(to_float_safe(10.5), 10.5)
        self.assertEqual(to_float_safe('10.5'), 10.5)

    def test_to_float_safe_decimal(self):
        """Test converting Decimal values."""
        self.assertEqual(to_float_safe(Decimal('10.5')), 10.5)
        self.assertEqual(to_float_safe(Decimal('0')), 0.0)

    def test_to_float_safe_none(self):
        """Test converting None returns default."""
        self.assertEqual(to_float_safe(None), 0.0)
        self.assertEqual(to_float_safe(None, default=5.0), 5.0)

    def test_to_float_safe_nan(self):
        """Test converting NaN returns default."""
        self.assertEqual(to_float_safe(float('nan')), 0.0)
        self.assertEqual(to_float_safe(float('nan'), default=-1.0), -1.0)

    def test_to_float_safe_invalid(self):
        """Test converting invalid values returns default."""
        self.assertEqual(to_float_safe('invalid'), 0.0)
        self.assertEqual(to_float_safe({}, default=0.0), 0.0)

    def test_format_decimal_fields_basic(self):
        """Test formatting decimal fields."""
        data = {
            'name': 'Test',
            'quantity': Decimal('10.5'),
            'price': Decimal('100')
        }
        result = format_decimal_fields(data, ['quantity', 'price'])

        self.assertEqual(result['name'], 'Test')
        self.assertEqual(result['quantity'], 10.5)
        self.assertEqual(result['price'], 100.0)
        self.assertIsInstance(result['quantity'], float)
        self.assertIsInstance(result['price'], float)

    def test_format_decimal_fields_missing(self):
        """Test formatting with missing fields."""
        data = {'name': 'Test', 'quantity': Decimal('10')}
        result = format_decimal_fields(data, ['quantity', 'missing_field'])

        self.assertEqual(result['quantity'], 10.0)
        self.assertNotIn('missing_field', result)

    def test_format_decimal_fields_original_unchanged(self):
        """Test that original data is not modified."""
        data = {'quantity': Decimal('10')}
        format_decimal_fields(data, ['quantity'])

        # Original should still have Decimal
        self.assertIsInstance(data['quantity'], Decimal)


class ExcelExportTests(TestCase):
    """Tests for Excel export functions."""

    def test_excel_report_builder_basic(self):
        """Test basic Excel report builder functionality."""
        builder = ExcelReportBuilder("Test Report")
        builder.add_headers(['Name', 'Value', 'Total'])
        builder.add_row(['Item 1', 100, 1000])
        builder.add_row(['Item 2', 200, 2000])
        builder.set_column_widths([20, 10, 15])

        buffer = builder.to_bytes()
        self.assertIsInstance(buffer, BytesIO)
        self.assertTrue(buffer.getvalue())

    def test_excel_report_builder_http_response(self):
        """Test creating HTTP response."""
        builder = ExcelReportBuilder("Test")
        builder.add_headers(['A', 'B'])
        builder.add_row([1, 2])

        response = builder.to_http_response('test.xlsx')

        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertIn('test.xlsx', response['Content-Disposition'])

    def test_excel_report_builder_multiple_sheets(self):
        """Test creating multiple sheets."""
        builder = ExcelReportBuilder("Sheet 1")
        builder.add_headers(['A', 'B'])
        builder.add_row([1, 2])

        builder.create_sheet("Sheet 2")
        builder.add_headers(['C', 'D'])
        builder.add_row([3, 4])

        buffer = builder.to_bytes()
        self.assertTrue(buffer.getvalue())

    def test_excel_report_builder_number_formats(self):
        """Test adding rows with number formats."""
        builder = ExcelReportBuilder("Test")
        builder.add_headers(['Name', 'Price', 'Percent'])
        builder.add_row(
            ['Item', 1234.56, 0.75],
            number_formats={2: '#,##0.00', 3: '0.00%'}
        )

        buffer = builder.to_bytes()
        self.assertTrue(buffer.getvalue())

    def test_create_excel_response_simple(self):
        """Test simple create_excel_response function."""
        headers = ['Name', 'Value']
        data = [['Item 1', 100], ['Item 2', 200]]

        response = create_excel_response(headers, data, 'test.xlsx')

        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    def test_excel_report_builder_chaining(self):
        """Test method chaining."""
        builder = (
            ExcelReportBuilder("Test")
            .add_headers(['A', 'B', 'C'])
            .add_row([1, 2, 3])
            .add_row([4, 5, 6])
            .set_column_widths([10, 10, 10])
        )

        buffer = builder.to_bytes()
        self.assertTrue(buffer.getvalue())
