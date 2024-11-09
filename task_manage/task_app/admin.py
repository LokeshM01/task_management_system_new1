# task_app/admin.py

from django.contrib import admin
from .models import Task, UserProfile, Department

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('task_id', 'assigned_by', 'assigned_to', 'department', 'deadline')
    search_fields = ('task_id', 'assigned_by__username', 'assigned_to__username')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'department', 'reports_to')
    search_fields = ('user__username', 'category')

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
