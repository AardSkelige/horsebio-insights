# backend/api/middleware.py
"""
Middleware для аутентификации API запросов и обработки ошибок.
"""
import logging
import traceback
import uuid
from typing import Callable, List, Optional

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import DatabaseError as DjangoDatabaseError

from api.exceptions import APIException

logger = logging.getLogger(__name__)


class APIErrorHandlerMiddleware:
    """
    Middleware for centralized error handling.
    Catches all exceptions and returns sanitized JSON responses.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_exception(
        self, request: HttpRequest, exception: Exception
    ) -> Optional[JsonResponse]:
        """
        Process exceptions and return appropriate JSON responses.
        Internal details are logged but not exposed to clients.
        """
        # Skip non-API paths
        if not (request.path.startswith('/api/') or request.path.startswith('/parser/')):
            return None

        # Generate unique error ID for tracking
        error_id = str(uuid.uuid4())[:8]

        # Handle our custom API exceptions
        if isinstance(exception, APIException):
            logger.warning(
                f"API error [{error_id}]: {exception.error_code} - {exception.message}",
                extra={
                    'error_id': error_id,
                    'path': request.path,
                    'method': request.method,
                    'error_code': exception.error_code,
                }
            )
            response_data = exception.to_dict()
            response_data['error_id'] = error_id
            return JsonResponse(response_data, status=exception.status_code)

        # Handle Django's ObjectDoesNotExist
        if isinstance(exception, ObjectDoesNotExist):
            logger.warning(
                f"Not found [{error_id}]: {request.path}",
                extra={'error_id': error_id, 'path': request.path}
            )
            return JsonResponse({
                'status': 'error',
                'message': 'Ресурс не найден',
                'code': 'NOT_FOUND',
                'error_id': error_id
            }, status=404)

        # Handle Django's PermissionDenied
        if isinstance(exception, PermissionDenied):
            logger.warning(
                f"Permission denied [{error_id}]: {request.path}",
                extra={'error_id': error_id, 'path': request.path}
            )
            return JsonResponse({
                'status': 'error',
                'message': 'Доступ запрещен',
                'code': 'PERMISSION_DENIED',
                'error_id': error_id
            }, status=403)

        # Handle database errors
        if isinstance(exception, DjangoDatabaseError):
            logger.error(
                f"Database error [{error_id}]: {str(exception)}",
                extra={'error_id': error_id, 'path': request.path},
                exc_info=True
            )
            return JsonResponse({
                'status': 'error',
                'message': 'Ошибка базы данных',
                'code': 'DATABASE_ERROR',
                'error_id': error_id
            }, status=500)

        # Handle all other exceptions - log full details but return generic message
        logger.error(
            f"Unhandled exception [{error_id}]: {type(exception).__name__}: {str(exception)}",
            extra={
                'error_id': error_id,
                'path': request.path,
                'method': request.method,
                'exception_type': type(exception).__name__,
            },
            exc_info=True  # This logs the full stack trace
        )

        # In debug mode, include more details
        if settings.DEBUG:
            return JsonResponse({
                'status': 'error',
                'message': f'{type(exception).__name__}: {str(exception)}',
                'code': 'INTERNAL_ERROR',
                'error_id': error_id,
                'traceback': traceback.format_exc()
            }, status=500)

        # In production, return generic error without internal details
        return JsonResponse({
            'status': 'error',
            'message': 'Внутренняя ошибка сервера',
            'code': 'INTERNAL_ERROR',
            'error_id': error_id
        }, status=500)


class APIAuthenticationMiddleware:
    """
    Middleware для проверки аутентификации на всех API endpoints,
    кроме публичных (login, check_auth).
    """

    # Пути, которые не требуют аутентификации
    PUBLIC_PATHS: List[str] = [
        '/api/auth/login/',
        '/api/auth/logout/',
        '/api/auth/check/',
        '/api/scripts/',   # Auth проверяется внутри view (сессия или X-Cron-Secret)
        '/parser/csrf/',   # CSRF token needed before login
        '/admin/',
        '/static/',
    ]

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Проверяем, нужна ли аутентификация для этого пути
        if self._requires_auth(request.path):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Требуется авторизация',
                    'code': 'UNAUTHORIZED'
                }, status=401)

            # Постраничные права: путь, принадлежащий странице, доступен только
            # при наличии этой страницы у пользователя (суперюзер — всё).
            from api.access import user_can_access_path
            if not user_can_access_path(request.user, request.path):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Нет доступа к этому разделу',
                    'code': 'FORBIDDEN'
                }, status=403)

            self._refresh_session(request)

        return self.get_response(request)

    def _refresh_session(self, request: HttpRequest) -> None:
        try:
            from django.utils import timezone
            from api.models import UserSession
            threshold = timezone.now() - timezone.timedelta(minutes=5)
            UserSession.objects.filter(
                session_key=request.session.session_key,
                last_seen_at__lt=threshold,
            ).update(last_seen_at=timezone.now())
        except Exception:
            pass

    def _requires_auth(self, path: str) -> bool:
        """Проверяет, требует ли путь аутентификации."""
        # Публичные пути не требуют аутентификации
        for public_path in self.PUBLIC_PATHS:
            if path.startswith(public_path):
                return False

        # Все остальные API пути требуют аутентификации
        if path.startswith('/api/'):
            return True

        # Parser endpoints тоже требуют аутентификации
        if path.startswith('/parser/'):
            return True

        # Остальные пути (admin, static и т.д.) не проверяем здесь
        return False
