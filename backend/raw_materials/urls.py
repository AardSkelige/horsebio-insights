from django.urls import path

from raw_materials import views

app_name = 'raw_materials'

urlpatterns = [
    path('', views.stock_list, name='stock-list'),
    path('refresh/', views.refresh, name='refresh'),
    path('issues/', views.issues, name='issues'),
]
