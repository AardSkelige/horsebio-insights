# ozon/urls.py
from django.urls import path
from . import views

app_name = 'ozon'

urlpatterns = [
    # Экспорт данных
    path('advertising/export/', views.export_advertising_data, name='export_advertising'),
    path('sales/export/', views.export_sales_data, name='export_sales'),

    # Аналитический отчет
    path('report/', views.generate_report, name='generate_report'),
    path('competitors/process/', views.process_competitors_info, name='process_competitors'),
    path('stock/process/', views.process_stock_availability, name='process_stock_availability'),
    path('fbo-converter/convert/', views.convert_fbo_supply, name='convert_fbo_supply'),
]
