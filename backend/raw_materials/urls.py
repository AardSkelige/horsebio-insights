from django.urls import path

from raw_materials import receipt_views, views

app_name = 'raw_materials'

urlpatterns = [
    path('', views.stock_list, name='stock-list'),
    path('refresh/', views.refresh, name='refresh'),
    path('issues/', views.issues, name='issues'),
    path('receipts/', receipt_views.receipts, name='receipts'),
    path('receipts/lines/<int:line_id>/', receipt_views.fill, name='receipt-fill'),
]
