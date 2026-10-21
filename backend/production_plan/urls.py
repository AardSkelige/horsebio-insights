from django.urls import path

from production_plan import views

app_name = 'production_plan'

urlpatterns = [
    path('', views.plan_view, name='plan'),
    path('refresh/', views.refresh, name='refresh'),
    path('export/', views.export, name='export'),
    path('exclusions/', views.exclusions, name='exclusions'),
    path('exclusions/<int:pk>/', views.exclusion_delete, name='exclusion-delete'),
    path('green/', views.green, name='green'),
]
