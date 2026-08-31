from django.urls import path

from . import views

app_name = 'ozon_logistics'

urlpatterns = [
    path('oauth/start/', views.oauth_start, name='oauth_start'),
    path('oauth/callback', views.oauth_callback, name='oauth_callback'),
    path('oauth/status/', views.oauth_status, name='oauth_status'),
    path('diag/', views.diagnostics, name='diagnostics'),
    path('diag/points/', views.diag_points, name='diag_points'),
    path('diag/point/', views.diag_point_info, name='diag_point_info'),
]
