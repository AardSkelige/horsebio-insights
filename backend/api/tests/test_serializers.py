"""
Tests for DRF serializers.
"""
from django.test import TestCase

from api.serializers import (
    DateRangeSerializer,
    PaginationSerializer,
    SortingSerializer,
    SearchFilterSerializer,
)


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
