from django.urls import path

from protocols import views

app_name = 'protocols'

urlpatterns = [
    path('tasks/', views.task_list, name='task-list'),
    path('tasks/<str:task_id>/', views.task_detail, name='task-detail'),
    path('tasks/<str:task_id>/docx/', views.task_docx, name='task-docx'),
    path('template-links/', views.link_template, name='link-template'),
    path('template-materials/', views.link_material, name='link-material'),
]
