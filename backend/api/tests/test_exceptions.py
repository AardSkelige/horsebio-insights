"""
Tests for custom API exceptions.
"""
from django.test import TestCase
from api.exceptions import (
    APIException,
    ValidationError,
    NotFoundError,
    AuthenticationError,
    PermissionDeniedError,
    ExternalServiceError,
    DataProcessingError,
)


class APIExceptionTests(TestCase):
    """Tests for base APIException class."""

    def test_default_message(self):
        """Test that default message is used when none provided."""
        exc = APIException()
        self.assertEqual(exc.message, "Внутренняя ошибка сервера")
        self.assertEqual(exc.status_code, 500)
        self.assertEqual(exc.error_code, "INTERNAL_ERROR")

    def test_custom_message(self):
        """Test that custom message overrides default."""
        exc = APIException(message="Custom error message")
        self.assertEqual(exc.message, "Custom error message")

    def test_details(self):
        """Test that details are included."""
        exc = APIException(details={"field": "value"})
        self.assertEqual(exc.details, {"field": "value"})

    def test_to_dict(self):
        """Test conversion to dictionary."""
        exc = APIException(
            message="Test error",
            details={"extra": "info"},
            error_code="TEST_ERROR"
        )
        result = exc.to_dict()

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'Test error')
        self.assertEqual(result['code'], 'TEST_ERROR')
        self.assertEqual(result['details'], {'extra': 'info'})

    def test_to_dict_without_details(self):
        """Test conversion to dictionary without details."""
        exc = APIException(message="Test error")
        result = exc.to_dict()

        self.assertNotIn('details', result)


class ValidationErrorTests(TestCase):
    """Tests for ValidationError."""

    def test_defaults(self):
        """Test default values."""
        exc = ValidationError()
        self.assertEqual(exc.message, "Ошибка валидации данных")
        self.assertEqual(exc.status_code, 400)
        self.assertEqual(exc.error_code, "VALIDATION_ERROR")

    def test_custom_message(self):
        """Test with custom message."""
        exc = ValidationError(message="Invalid email format")
        self.assertEqual(exc.message, "Invalid email format")


class NotFoundErrorTests(TestCase):
    """Tests for NotFoundError."""

    def test_defaults(self):
        """Test default values."""
        exc = NotFoundError()
        self.assertEqual(exc.message, "Ресурс не найден")
        self.assertEqual(exc.status_code, 404)
        self.assertEqual(exc.error_code, "NOT_FOUND")

    def test_custom_message(self):
        """Test with custom message."""
        exc = NotFoundError(message="Материал не найден")
        self.assertEqual(exc.message, "Материал не найден")


class AuthenticationErrorTests(TestCase):
    """Tests for AuthenticationError."""

    def test_defaults(self):
        """Test default values."""
        exc = AuthenticationError()
        self.assertEqual(exc.message, "Ошибка аутентификации")
        self.assertEqual(exc.status_code, 401)
        self.assertEqual(exc.error_code, "AUTHENTICATION_ERROR")


class PermissionDeniedErrorTests(TestCase):
    """Tests for PermissionDeniedError."""

    def test_defaults(self):
        """Test default values."""
        exc = PermissionDeniedError()
        self.assertEqual(exc.message, "Доступ запрещен")
        self.assertEqual(exc.status_code, 403)
        self.assertEqual(exc.error_code, "PERMISSION_DENIED")


class ExternalServiceErrorTests(TestCase):
    """Tests for ExternalServiceError."""

    def test_defaults(self):
        """Test default values."""
        exc = ExternalServiceError()
        self.assertEqual(exc.message, "Ошибка внешнего сервиса")
        self.assertEqual(exc.status_code, 502)
        self.assertEqual(exc.error_code, "EXTERNAL_SERVICE_ERROR")


class DataProcessingErrorTests(TestCase):
    """Tests for DataProcessingError."""

    def test_defaults(self):
        """Test default values."""
        exc = DataProcessingError()
        self.assertEqual(exc.message, "Ошибка обработки данных")
        self.assertEqual(exc.status_code, 500)
        self.assertEqual(exc.error_code, "DATA_PROCESSING_ERROR")
