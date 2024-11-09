from django.shortcuts import render, redirect, get_object_or_404
from .models import Task, UserProfile, Department
from django.contrib.auth.decorators import login_required
from .forms import TaskForm, TaskStatusUpdateForm, AssigneeCommentForm
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timedelta
from django.http import JsonResponse

@login_required
def home(request):
    # Display tasks assigned to the Departmental Manager's team
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.category == 'Departmental Manager':
        # Fetch tasks based on department or any specific criteria
        tasks = Task.objects.filter(department=user_profile.department)
        return render(request, 'tasks/home.html', {'tasks': tasks})
    return redirect('assigned_to_me')

@login_required
def assigned_to_me(request):
    # Display tasks assigned to the current user
    tasks = Task.objects.filter(assigned_to=request.user)
    return render(request, 'tasks/assigned_to_me.html', {'tasks': tasks})

@login_required
def assigned_by_me(request):
    # Display tasks created/assigned by the current user
    tasks = Task.objects.filter(assigned_by=request.user)
    return render(request, 'tasks/assigned_by_me.html', {'tasks': tasks})

@login_required
def user_profile(request):
    # Display user profile details
    user_profile = UserProfile.objects.get(user=request.user)
    return render(request, 'tasks/user_profile.html', {'user_profile': user_profile})

@login_required
def view_system_logs(request):
    # Placeholder for viewing system logs
    logs = ["Error 1: Task sync issue.", "Error 2: User permissions mismatch."]
    return render(request, 'tasks/system_logs.html', {'logs': logs})

def custom_403_view(request, exception=None):
    # Custom 403 Forbidden view to show a custom access denied message
    return render(request, '403.html', status=403)

@login_required
def task_list(request):
    """
    Display task list with filtering options for Task Management System Managers.
    For other users, display only tasks created by or assigned to them.
    """
    user_profile = UserProfile.objects.get(user=request.user)

    if user_profile.category == 'Task Management System Manager':
        tasks = Task.objects.all()  # Start with all tasks

        # Apply filters if provided
        department_id = request.GET.get('department')
        if department_id:
            tasks = tasks.filter(department_id=department_id)

        person_id = request.GET.get('person')
        if person_id:
            tasks = tasks.filter(Q(assigned_by_id=person_id) | Q(assigned_to_id=person_id))

        ageing_days = request.GET.get('ageing_days')
        if ageing_days:
            today = datetime.today().date()
            if ageing_days == 'overdue':
                tasks = tasks.filter(deadline__lt=today, status_update_assignee__in=['Not Started', 'In Progress'])
            else:
                ageing_days = int(ageing_days)
                tasks = tasks.filter(assigned_date__lte=today - timedelta(days=ageing_days))

        status = request.GET.get('status')
        if status:
            tasks = tasks.filter(status_update_assignee=status)

        departments = Department.objects.all()
        users = UserProfile.objects.filter(user__is_active=True)
        status_choices = TaskForm.STATUS_CHOICES

        return render(request, 'tasks/task_list.html', {
            'tasks': tasks,
            'departments': departments,
            'users': users,
            'status_choices': status_choices,
        })

    else:
        created_tasks = Task.objects.filter(assigned_by=request.user)
        assigned_tasks = Task.objects.filter(assigned_to=request.user)
        return render(request, 'tasks/task_list.html', {
            'created_tasks': created_tasks,
            'assigned_tasks': assigned_tasks,
        })

@login_required
def create_task(request):
    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.assigned_by = request.user
            task.department = UserProfile.objects.get(user=task.assigned_to).department
            task.save()
            return JsonResponse({'message': 'Task created successfully!', 'task_id': task.task_id})
        else:
            return JsonResponse({'error': 'Form data is invalid', 'errors': form.errors}, status=400)
    else:
        form = TaskForm(user=request.user)
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
    task = get_object_or_404(Task, task_id=task_id)
    if task.assigned_to != request.user:
        raise PermissionDenied("Only the assignee can update this task.")

    if request.method == 'POST':
        form = TaskStatusUpdateForm(request.POST, instance=task)
        comment_form = AssigneeCommentForm(request.POST, instance=task)
        if form.is_valid() and comment_form.is_valid():
            form.save()
            comment_form.save()
            return redirect('task_detail', task_id=task.task_id)

    else:
        form = TaskStatusUpdateForm(instance=task)
        comment_form = AssigneeCommentForm(instance=task)

    return render(request, 'tasks/update_task_status.html', {
        'form': form,
        'comment_form': comment_form,
        'task': task,
    })

@login_required
def mark_task_completed(request, task_id):
    task = get_object_or_404(Task, task_id=task_id)
    if task.assigned_by != request.user:
        raise PermissionDenied("Only the creator can mark this task as completed.")

    task.status_update_assignor = 'Completed'
    task.status_update_assignee = 'Completed'
    task.save()
    
    return redirect('task_detail', task_id=task.task_id)

@login_required
def reassign_task(request, task_id):
    task = get_object_or_404(Task, task_id=task_id)
    if task.assigned_to != request.user:
        raise PermissionDenied("Only the assignee can reassign the task back to the creator.")

    task.assigned_to = task.assigned_by
    task.save()

    return redirect('task_detail', task_id=task.task_id)

@login_required
def dashboard(request):
    user_profile = UserProfile.objects.get(user=request.user)

    # Redirect based on user category
    if user_profile.category == 'Departmental Manager':
        return redirect('home')  # Redirect Departmental Managers to Home Page
    else:
        return redirect('assigned_to_me')  # Redirect other users to Assigned To Me Page

