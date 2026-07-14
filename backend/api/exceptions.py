"""
Custom exception classes for the API.
These exceptions provide structured error handling without exposing internal details.
"""
from typing import Optional, Dict, Any


class APIException(Exception):
    """
    Base exception class for all API errors.
    Subclasses should define default_message and status_code.
    """
    default_message: str = "Внутренняя ошибка сервера"
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None
    ):
        self.message = message or self.default_message
        self.details = details or {}
        if error_code:
            self.error_code = error_code
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to a dictionary for JSON response."""
        result = {
            'status': 'error',
            'message': self.message,
            'code': self.error_code
        }
        if self.details:
            result['details'] = self.details
        return result


class ValidationError(APIException):
    """Raised when input validation fails."""
    default_message = "Ошибка валидации данных"
    status_code = 400
    error_code = "VALIDATION_ERROR"


class NotFoundError(APIException):
    """Raised when a requested resource is not found."""
    default_message = "Ресурс не найден"
    status_code = 404
    error_code = "NOT_FOUND"


class AuthenticationError(APIException):
    """Raised when authentication fails."""
    default_message = "Ошибка аутентификации"
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"


class PermissionDeniedError(APIException):
    """Raised when a user doesn't have permission for an action."""
    default_message = "Доступ запрещен"
    status_code = 403
    error_code = "PERMISSION_DENIED"


class ConflictError(APIException):
    """Raised when there's a conflict with existing data."""
    default_message = "Конфликт данных"
    status_code = 409
    error_code = "CONFLICT"


class ExternalServiceError(APIException):
    """Raised when an external service (e.g., MoySklad API) fails."""
    default_message = "Ошибка внешнего сервиса"
    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"


class RateLimitError(APIException):
    """Raised when rate limit is exceeded."""
    default_message = "Превышен лимит запросов"
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


class DatabaseError(APIException):
    """Raised when a database operation fails."""
    default_message = "Ошибка базы данных"
    status_code = 500
    error_code = "DATABASE_ERROR"


class DataProcessingError(APIException):
    """Raised when data processing/calculation fails."""
    default_message = "Ошибка обработки данных"
    status_code = 500
    error_code = "DATA_PROCESSING_ERROR"
