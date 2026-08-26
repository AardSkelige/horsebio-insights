# config/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Административная панель Django
    path('admin/', admin.site.urls),

    # API endpoints
    path('api/', include([
        # Основные API endpoints
        path('', include('api.urls', namespace='api')),

        # Endpoints для Ozon аналитики
        path('ozon/', include('ozon.urls', namespace='ozon')),

        # Ozon Доставка — отдельный контур с OAuth-авторизацией
        path('ozon-logistics/', include('ozon_logistics.urls', namespace='ozon_logistics')),

    ])),

    # Endpoints для синхронизации МойСклад
    path('parser/', include('sync.urls', namespace='parser')),
]
