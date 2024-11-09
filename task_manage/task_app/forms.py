# task_app/forms.py

from django import forms
from django.contrib.auth.models import User
from .models import Task, UserProfile

class TaskForm(forms.ModelForm):
    """
    Form for creating and editing tasks, used by managers and executives.
    """
    STATUS_CHOICES = [
        ('Not Started', 'Not Started'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Stalled', 'Stalled'),
        ('On-Hold', 'On-Hold'),
        ('Cancelled', 'Cancelled'),
    ]

    class Meta:
        model = Task
        fields = [
            'assigned_to', 'deadline', 'revised_completion_date', 'reasons_for_revision',
            'task_summary', 'supporting_files', 'task_category_functional', 'task_category_priority',
            'status_update_assignor', 'comments_by_manager'
        ]
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date'}),
            'revised_completion_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        # Extract the current user from kwargs
        user = kwargs.pop('user', None)
        super(TaskForm, self).__init__(*args, **kwargs)

        # Only filter the assigned_to field if a user is provided
        if user:
            user_profile = UserProfile.objects.get(user=user)

            # If the user is a Departmental Manager, apply specific filters
            if user_profile.category == 'Departmental Manager':
                # Filter to include only Non-Management in the same department or Departmental Managers across all departments
                self.fields['assigned_to'].queryset = User.objects.filter(
                    userprofile__category__in=['Non-Management', 'Departmental Manager']
                ).filter(
                    userprofile__department=user_profile.department
                ) | User.objects.filter(
                    userprofile__category='Departmental Manager'
                )

            # Executive Management should see all users
            elif user_profile.category == 'Executive Management':
                self.fields['assigned_to'].queryset = User.objects.all()

class TaskStatusUpdateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['status_update_assignee']

class AssigneeCommentForm(forms.ModelForm):
    """
    Form for assignees to add comments to a task.
    """
    class Meta:
        model = Task
        fields = ['comments_by_assignee']  # Only allow adding comments
        widgets = {
            'comments_by_assignee': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        }
