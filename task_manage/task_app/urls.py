# task_app/urls.py

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.conf.urls import handler403
from task_app import views as app_views

handler403 = app_views.custom_403_view

urlpatterns = [
    path('create/', views.create_task, name='create_task'),  # Task creation URL remains the same
    path('edit/<str:task_id>/', views.edit_task, name='edit_task'),
    path('update_status/<str:task_id>/', views.update_task_status, name='update_task_status'),
    path('profile/', views.profile, name='profile'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('system_logs/', views.view_system_logs, name='view_system_logs'),
    path('detail/<str:task_id>/', views.task_detail, name='task_detail'),  # Ensure this line exists
    # New paths for task completion and reassignment
    path('complete/<str:task_id>/', views.mark_task_completed, name='mark_task_completed'),
    path('reassign/<str:task_id>/', views.reassign_task, name='reassign_task'),
]
