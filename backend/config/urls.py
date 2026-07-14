# config/urls.py
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    # Административная панель Django
    path('admin/', admin.site.urls),

    # API endpoints
    path('api/', include([
        # Основные API endpoints
        path('', include('api.urls', namespace='api')),

        # Endpoints для Ozon аналитики
        path('ozon/', include('ozon.urls', namespace='ozon')),

        # OpenAPI Schema and Documentation
        path('schema/', SpectacularAPIView.as_view(), name='schema'),
        path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ])),

    # Endpoints для синхронизации МойСклад
    path('parser/', include('sync.urls', namespace='parser')),
]