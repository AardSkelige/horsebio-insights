# sync/urls.py

from django.urls import path
from . import views

app_name = 'parser'  # Keep namespace for URL compatibility

urlpatterns = [
    path('', views.home, name='home'),
    path('load-data/', views.load_data, name='load_data'),
    path('stream-progress/', views.stream_loading_progress, name='stream_progress'),
    path('stop-loading/', views.stop_loading, name='stop_loading'),
    path('task-status/', views.get_task_status, name='get_task_status'),
    path('csrf/', views.get_csrf_token, name='get_csrf_token'),
]
