"""
Tests for API middleware.
"""
import json
from unittest.mock import Mock, patch
from django.test import TestCase, RequestFactory, override_settings
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import DatabaseError

from api.middleware import APIErrorHandlerMiddleware
from api.exceptions import NotFoundError, ValidationError, DataProcessingError


class APIErrorHandlerMiddlewareTests(TestCase):
    """Tests for APIErrorHandlerMiddleware."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = RequestFactory()
        self.get_response = Mock(return_value=JsonResponse({'status': 'success'}))
        self.middleware = APIErrorHandlerMiddleware(self.get_response)

    def test_normal_request_passes_through(self):
        """Test that normal requests pass through unchanged."""
        request = self.factory.get('/api/test/')
        response = self.middleware(request)

        self.get_response.assert_called_once_with(request)
        self.assertEqual(response.status_code, 200)

    def test_non_api_path_exception_not_handled(self):
        """Test that exceptions on non-API paths are not handled."""
        request = self.factory.get('/admin/')
        exception = ValueError("Test error")

        result = self.middleware.process_exception(request, exception)

        self.assertIsNone(result)

    def test_api_exception_handled(self):
        """Test that custom API exceptions are handled correctly."""
        request = self.factory.get('/api/test/')
        exception = NotFoundError("Материал не найден")

        response = self.middleware.process_exception(request, exception)

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['message'], 'Материал не найден')
        self.assertEqual(data['code'], 'NOT_FOUND')
        self.assertIn('error_id', data)

    def test_validation_error_handled(self):
        """Test that validation errors return 400."""
        request = self.factory.get('/api/test/')
        exception = ValidationError("Invalid input")

        response = self.middleware.process_exception(request, exception)

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertEqual(data['code'], 'VALIDATION_ERROR')

    def test_data_processing_error_handled(self):
        """Test that data processing errors return 500."""
        request = self.factory.get('/api/test/')
        exception = DataProcessingError("Processing failed")

        response = self.middleware.process_exception(request, exception)

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertEqual(data['code'], 'DATA_PROCESSING_ERROR')

    def test_django_does_not_exist_handled(self):
        """Test that Django's ObjectDoesNotExist is handled."""
        request = self.factory.get('/api/test/')
        exception = ObjectDoesNotExist("Not found")

        response = self.middleware.process_exception(request, exception)

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertEqual(data['code'], 'NOT_FOUND')

    def test_django_permission_denied_handled(self):
        """Test that Django's PermissionDenied is handled."""
        request = self.factory.get('/api/test/')
        exception = PermissionDenied("Access denied")

        response = self.middleware.process_exception(request, exception)

        self.assertEqual(response.status_code, 403)
        data = json.loads(response.content)
        self.assertEqual(data['code'], 'PERMISSION_DENIED')

    def test_database_error_handled(self):
        """Test that database errors are handled."""
        request = self.factory.get('/api/test/')
        exception = DatabaseError("Database connection failed")

        response = self.middleware.process_exception(request, exception)

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertEqual(data['code'], 'DATABASE_ERROR')

    @override_settings(DEBUG=False)
    def test_generic_exception_sanitized_in_production(self):
        """Test that generic exceptions are sanitized in production."""
        request = self.factory.get('/api/test/')
        exception = ValueError("Internal error details")

        response = self.middleware.process_exception(request, exception)

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertEqual(data['message'], 'Внутренняя ошибка сервера')
        self.assertEqual(data['code'], 'INTERNAL_ERROR')
        self.assertNotIn('traceback', data)
        self.assertNotIn('Internal error details', data['message'])

    @override_settings(DEBUG=True)
    def test_generic_exception_detailed_in_debug(self):
        """Test that generic exceptions include details in debug mode."""
        request = self.factory.get('/api/test/')
        exception = ValueError("Internal error details")

        response = self.middleware.process_exception(request, exception)

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertIn('Internal error details', data['message'])
        self.assertIn('traceback', data)

    def test_error_id_generated(self):
        """Test that unique error ID is generated."""
        request = self.factory.get('/api/test/')
        exception = NotFoundError()

        response = self.middleware.process_exception(request, exception)

        data = json.loads(response.content)
        self.assertIn('error_id', data)
        self.assertEqual(len(data['error_id']), 8)  # UUID[:8]

    def test_parser_path_handled(self):
        """Test that /parser/ paths are also handled."""
        request = self.factory.get('/parser/sync/')
        exception = DataProcessingError("Sync failed")

        response = self.middleware.process_exception(request, exception)

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertEqual(data['code'], 'DATA_PROCESSING_ERROR')
