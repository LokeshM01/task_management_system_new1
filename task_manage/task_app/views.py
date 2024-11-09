# task_app/views.py

from django.shortcuts import render, redirect, get_object_or_404
from .models import Task, UserProfile, Department
from django.contrib.auth.decorators import login_required
from .forms import TaskForm, TaskStatusUpdateForm, AssigneeCommentForm
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from django.db.models import Q
from django.utils import timezone

@login_required
def view_system_logs(request):
    # Placeholder for viewing system logs
    logs = ["Error 1: Task sync issue.", "Error 2: User permissions mismatch."]
    
    return render(request, 'tasks/system_logs.html', {'logs': logs})

def custom_403_view(request, exception=None):
    """Custom 403 Forbidden view to show a custom access denied message."""
    return render(request, '403.html', status=403)

@login_required
def task_list(request):
    """
    Display task list with filtering options for Task Management System Managers.
    For other users, display only tasks created by or assigned to them.
    """
    user_profile = UserProfile.objects.get(user=request.user)

    # If user is a Task Management System Manager, provide full access with filters
    if user_profile.category == 'Task Management System Manager':
        tasks = Task.objects.all()  # Start with all tasks

        # Apply department filter if provided
        department_id = request.GET.get('department')
        if department_id:
            tasks = tasks.filter(department_id=department_id)

        # Apply person filter (Assignee or Assignor) if provided
        person_id = request.GET.get('person')
        if person_id:
            tasks = tasks.filter(Q(assigned_by_id=person_id) | Q(assigned_to_id=person_id))

        # Apply ageing filter for tasks open for certain days or delayed
        ageing_days = request.GET.get('ageing_days')
        if ageing_days:
            today = datetime.today().date()
            if ageing_days == 'overdue':  # For overdue tasks beyond their deadline
                tasks = tasks.filter(deadline__lt=today, status_update_assignee__in=['Not Started', 'In Progress'])
            else:  # For tasks open for a specific number of days
                ageing_days = int(ageing_days)
                tasks = tasks.filter(assigned_date__lte=today - timedelta(days=ageing_days))

        # Apply task status filter if provided
        status = request.GET.get('status')
        if status:
            tasks = tasks.filter(status_update_assignee=status)

        # Get departments, users, and status choices for filter options in the template
        departments = Department.objects.all()
        users = UserProfile.objects.filter(user__is_active=True)
        status_choices = TaskForm.STATUS_CHOICES

        return render(request, 'tasks/task_list.html', {
            'tasks': tasks,
            'departments': departments,
            'users': users,
            'status_choices': status_choices,
        })

    # For non-Task Management System Managers, show only their created or assigned tasks
    else:
        created_tasks = Task.objects.filter(assigned_by=request.user)  # Tasks created by the user
        assigned_tasks = Task.objects.filter(assigned_to=request.user)  # Tasks assigned to the user
        return render(request, 'tasks/task_list.html', {
            'created_tasks': created_tasks,
            'assigned_tasks': assigned_tasks,
        })

@login_required
def profile(request):
    user_profile = UserProfile.objects.get(user=request.user)

    if user_profile.category == 'Task Management System Manager':
        # Fetch all tasks, departments, and users
        all_tasks = Task.objects.all()
        all_users = UserProfile.objects.select_related('user').all()  # Ensuring 'user' field is accessible
        departments = Department.objects.all()

        # Get filter values from the GET request
        department_filter = request.GET.get('department')
        person_filter = request.GET.get('person')
        ageing_days_filter = request.GET.get('ageing_days')
        status_filter = request.GET.get('status')

        # Apply filters if specified
        if department_filter:
            all_tasks = all_tasks.filter(department__id=department_filter)

        if person_filter:
            all_tasks = all_tasks.filter(Q(assigned_to__id=person_filter) | Q(assigned_by__id=person_filter))

        if ageing_days_filter:
            if ageing_days_filter == 'overdue':
                all_tasks = all_tasks.filter(deadline__lt=timezone.now())
            else:
                days_open = int(ageing_days_filter)
                all_tasks = all_tasks.filter(deadline__gte=timezone.now() - timedelta(days=days_open))

        if status_filter:
            all_tasks = all_tasks.filter(status_update_assignee=status_filter)

        # Status choices for dropdown
        status_choices = [
            ('Not Started', 'Not Started'),
            ('In Progress', 'In Progress'),
            ('Completed', 'Completed'),
            ('Stalled', 'Stalled'),
            ('On-Hold', 'On-Hold'),
            ('Cancelled', 'Cancelled'),
        ]

        # Pass all data to the template
        return render(request, 'registration/profile.html', {
            'all_tasks': all_tasks,
            'all_users': all_users,
            'departments': departments,
            'status_choices': status_choices,
            'is_manager': True,
        })

    else:
        # For regular users, show tasks they created or are assigned to
        created_tasks = Task.objects.filter(assigned_by=request.user)
        assigned_tasks = Task.objects.filter(assigned_to=request.user)

        return render(request, 'registration/profile.html', {
            'created_tasks': created_tasks,
            'assigned_tasks': assigned_tasks,
            'is_manager': False,
        })



@login_required
def create_task(request):
    user_profile = UserProfile.objects.get(user=request.user)

    # Check if the current user has permission to create tasks
    if user_profile.category not in ['Executive Management', 'Departmental Manager']:
        raise PermissionDenied

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, user=request.user)  # Pass the user to the form
        if form.is_valid():
            task = form.save(commit=False)
            task.assigned_by = request.user
            assignee_profile = UserProfile.objects.get(user=task.assigned_to)

            # Check assignment permissions
            if user_profile.category == 'Departmental Manager':
                if assignee_profile.category == 'Non-Management' and assignee_profile.department == user_profile.department:
                    task.department = assignee_profile.department
                elif assignee_profile.category == 'Departmental Manager':
                    task.department = assignee_profile.department
                else:
                    raise PermissionDenied("You can only assign tasks to Non-Management in your department or Departmental Managers.")

            # Executive Management has no restrictions
            else:
                task.department = assignee_profile.department

            task.save()
            return redirect('task_detail', task_id=task.task_id)
    else:
        form = TaskForm(user=request.user)  # Pass the user to the form
    return render(request, 'tasks/create_task.html', {'form': form})

@login_required
def edit_task(request, task_id):
    task = get_object_or_404(Task, task_id=task_id)
    if task.assigned_by != request.user:
        raise PermissionDenied

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, instance=task)
        if form.is_valid():
            form.save()
            return redirect('task_detail', task_id=task.task_id)
    else:
        form = TaskForm(instance=task)
    return render(request, 'tasks/edit_task.html', {'form': form})

@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, task_id=task_id)
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.category == 'Task Management System Manager' or \
       task.assigned_by == request.user or \
       task.assigned_to == request.user:
        return render(request, 'tasks/task_detail.html', {'task': task})
    else:
        raise PermissionDenied

@login_required
def update_task_status(request, task_id):
    """
    Allows task assignees (Non-Management Staff) to update the task status and add comments.
    Only the assigned user (assignee) can make updates to the status and comments fields.
    """
    task = get_object_or_404(Task, task_id=task_id)
    
    # Ensure only the assigned user (assignee) can update the task
    if task.assigned_to != request.user:
        raise PermissionDenied

    # Process form submission
    if request.method == 'POST':
        form = TaskStatusUpdateForm(request.POST, instance=task)
        comment_form = AssigneeCommentForm(request.POST, instance=task)
        
        # Check if both forms are valid
        if form.is_valid() and comment_form.is_valid():
            form.save()  # Save the status update
            comment_form.save()  # Save the assignee's comment
            return redirect('task_detail', task_id=task.task_id)
    
    # For GET requests, display the forms pre-filled with current data
    else:
        form = TaskStatusUpdateForm(instance=task)  # Form for updating task status
        comment_form = AssigneeCommentForm(instance=task)  # Form for adding comments
    
    return render(request, 'tasks/update_task_status.html', {
        'form': form,
        'comment_form': comment_form,
        'task': task
    })



@login_required
def dashboard(request):
    """
    Redirect users to the appropriate page based on their role:
    - Non-Management Staff -> Profile Page
    - Others (e.g., Executive, Department Manager) -> Create Task Page
    """
    user_profile = UserProfile.objects.get(user=request.user)

    # Check the user's category and redirect accordingly
    if user_profile.category == 'Non-Management':
        # Non-Management Staff are redirected to their profile
        return redirect('profile')
    else:
        # Executive and Department Managers are redirected to create a task
        return redirect('create_task')
