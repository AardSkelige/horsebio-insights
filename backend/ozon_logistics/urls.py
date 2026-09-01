from django.urls import path

from . import site_api, views

app_name = 'ozon_logistics'

urlpatterns = [
    path('oauth/start/', views.oauth_start, name='oauth_start'),
    path('oauth/callback', views.oauth_callback, name='oauth_callback'),
    path('oauth/status/', views.oauth_status, name='oauth_status'),
    path('diag/', views.diagnostics, name='diagnostics'),
    path('diag/points/', views.diag_points, name='diag_points'),
    path('diag/point/', views.diag_point_info, name='diag_point_info'),
    path('diag/warehouses/', views.diag_warehouses, name='diag_warehouses'),
    path('diag/products/', views.diag_products, name='diag_products'),
    path('diag/checkout/', views.diag_checkout, name='diag_checkout'),
    path('diag/cancel/', views.diag_cancel, name='diag_cancel'),

    # Публичные — их вызывает корзина horse-bio.ru из браузера покупателя
    path('site/availability/', site_api.availability, name='site_availability'),
    path('site/points/', site_api.points, name='site_points'),
    path('site/point/<int:map_point_id>/', site_api.point_details, name='site_point_details'),
    path('site/quote/', site_api.quote, name='site_quote'),
]
