from django.shortcuts import render, redirect, get_object_or_404
from .models import Task, UserProfile, Department
from django.contrib.auth.decorators import login_required
from .forms import TaskForm
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.http import HttpResponse
from .models import ActivityLog
import csv
import pandas as pd
from django.db.models import Count
from .forms import TaskStatusUpdateForm
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.timezone import now
from .tasks import send_deadline_reminders_logic, notify_overdue_tasks_logic

def send_email_notification(subject, template_name, context, recipient_email):
    """Utility function to send email notifications."""
    email_body = render_to_string(template_name, context)
    send_mail(
        subject,
        '',  # Empty string since we're using HTML
        'no-reply@yourdomain.com',  # Replace with your email
        [recipient_email],
        html_message=email_body,
        fail_silently=False,
    )

@login_required
def home(request):
    user_profile = UserProfile.objects.get(user=request.user)

    if user_profile.category == 'Departmental Manager':
        # Fetch all tasks related to the department of the manager
        department = user_profile.department
        tasks = Task.objects.filter(
            # Tasks created by members of the manager's department
            Q(assigned_by__userprofile__department=department) |
            # Tasks assigned to members of the manager's department
            Q(assigned_to__userprofile__department=department)
        )
        return render(request, 'tasks/home.html', {
            'tasks': tasks,
            'departments': Department.objects.all(),
            
        })

    return redirect('assigned_to_me')

@login_required
def assigned_to_me(request):
    # Filter tasks where the assigned_to field matches the current user
    tasks = Task.objects.filter(assigned_to=request.user)

    # Passing task category functional choices (department in this case) for filtering
    functional_categories = Task.FUNCTIONAL_CATEGORIES  # Assuming Task.FUNCTIONAL_CATEGORIES holds department choices

    # Render the template with the tasks and functional categories
    return render(request, 'tasks/assigned_to_me.html', {
        'tasks': tasks,
        'departments': Department.objects.all(),
        'users':User.objects.all(),
    })

@login_required
def assigned_by_me(request):
    # Fetch tasks where the logged-in user is the assigner
    tasks = Task.objects.filter(assigned_by=request.user)

    # Passing task category functional choices (department in this case) for filtering
    functional_categories = Task.FUNCTIONAL_CATEGORIES  # Assuming Task.FUNCTIONAL_CATEGORIES holds department choices

    # Render the template with the tasks and functional categories
    return render(request, 'tasks/assigned_by_me.html', {
        'tasks': tasks,
        'departments': Department.objects.all(),
        'users':User.objects.all(),
    })

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
            task.assigned_by = request.user  # Automatically set the assigned_by field
            task.save()

            # Notify the departmental manager (if exists)
            if task.department and hasattr(task.department, 'manager') and task.department.manager:
                manager_email = task.department.manager.email  # Ensure the manager's email exists
                view_ticket_url = request.build_absolute_uri(f'/tasks/{task.task_id}/detail/')
                context = {
                    'user': task.department.manager,
                    'ticket': task,
                    'view_ticket_url': view_ticket_url,
                }
                send_email_notification(
                    subject="New Task Created in Your Department",
                    template_name='emails/ticket_created.html',
                    context=context,
                    recipient_email=manager_email,
                )

            # Notify the assignee (if assigned)
            if task.assigned_to:
                assignee_email = task.assigned_to.email
                view_ticket_url = request.build_absolute_uri(f'/tasks/{task.task_id}/detail/')
                context = {
                    'user': task.assigned_to,
                    'ticket': task,
                    'view_ticket_url': view_ticket_url,
                }
                send_email_notification(
                    subject="You Have Been Assigned a New Task",
                    template_name='emails/ticket_assigned.html',
                    context=context,
                    recipient_email=assignee_email,
                )

             # Notify the task creator
            creator_email = task.assigned_by.email
            view_ticket_url = request.build_absolute_uri(f'/tasks/{task.task_id}/detail/')
            context = {
                'user': task.assigned_by,
                'ticket': task,
                'view_ticket_url': view_ticket_url,
            }
            send_email_notification(
                subject="Your Task Has Been Created",
                template_name='emails/task_created_by_you.html',
                context=context,
                recipient_email=creator_email,
            )

            # Log the creation action
            ActivityLog.objects.create(
                action='created',
                user=request.user,
                task=task,
                description=f"Task {task.task_id} created by {request.user.username} for {task.assigned_to.username if task.assigned_to else 'Unassigned'}"
            )
            return JsonResponse({'message': 'Task created successfully!', 'task_id': task.task_id})
        else:
            # Log invalid form errors
            return JsonResponse({'error': 'Form data is invalid', 'errors': form.errors}, status=400)
    else:
        form = TaskForm(user=request.user)
        return render(request, 'tasks/create_task.html', {'form': form})


@login_required
def edit_task(request, task_id):
    task = get_object_or_404(Task, task_id=task_id)
    if task.assigned_by != request.user:
        raise PermissionDenied

    old_priority = task.priority  # Capture the current priority before changes
    old_status = task.status

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, instance=task)
        if form.is_valid():
            updated_task = form.save()

            if old_status != updated_task.status:
                ActivityLog.objects.create(
                    action='status_changed',
                    user=request.user,
                    task=task,
                    description=f"Status changed from '{old_status}' to '{updated_task.status}'"
                )

            # Log priority change if it was updated
            if old_priority != task.priority:
                ActivityLog.objects.create(
                    action='priority_changed',
                    user=request.user,
                    task=task,
                    description=f"Priority changed from {old_priority} to {task.priority}"
                )

            return redirect('assigned_by_me')
    else:
        form = TaskForm(instance=task)

    return render(request, 'tasks/edit_task.html', {'task': task, 'form': form})


@login_required
def task_detail(request, task_id):
    task = get_object_or_404(Task, task_id=task_id)
    user_profile = UserProfile.objects.get(user=request.user)
    return render(request, 'tasks/task_detail.html', {'task': task})

@login_required
def update_task_status(request, task_id):
    task = get_object_or_404(Task, task_id=task_id)

    old_deadline = task.revised_completion_date
    old_comments = task.comments_by_assignee

    if request.method == 'POST':
        form = TaskStatusUpdateForm(request.POST, instance=task)
        if form.is_valid():
            form.save()

            view_ticket_url = request.build_absolute_uri(f'/tasks/{task.task_id}/detail/')
            context = {
                'ticket': task,
                'view_ticket_url': view_ticket_url,
            }

            # Notify about deadline revision
            if old_deadline != task.revised_completion_date:
                context['update_message'] = f"The deadline has been revised to {task.revised_completion_date}"
                if task.assigned_by:
                    send_email_notification(
                        subject=f"Deadline Revised: {task.task_id}",
                        template_name='emails/ticket_deadline_updated.html',
                        context=context,
                        recipient_email=task.assigned_by.email,
                    )
                if task.assigned_to:
                    send_email_notification(
                        subject=f"Deadline Revised: {task.task_id}",
                        template_name='emails/ticket_deadline_updated.html',
                        context=context,
                        recipient_email=task.assigned_to.email,
                    )

            # Notify about comment updates
            if old_comments != task.comments_by_assignee:
                context['update_message'] = f"New comment: {task.comments_by_assignee}"
                if task.assigned_by:
                    send_email_notification(
                        subject=f"Comment Updated: {task.task_id}",
                        template_name='emails/ticket_comment_updated.html',
                        context=context,
                        recipient_email=task.assigned_by.email,
                    )
                if task.assigned_to:
                    send_email_notification(
                        subject=f"Comment Updated: {task.task_id}",
                        template_name='emails/ticket_comment_updated.html',
                        context=context,
                        recipient_email=task.assigned_to.email,
                    )

            # Log deadline revision
            if old_deadline != task.revised_completion_date:
                ActivityLog.objects.create(
                    action='deadline_revised',
                    user=request.user,
                    task=task,
                    description=f"Deadline revised from {old_deadline} to {task.revised_completion_date}"
                )

            # Log comment addition
            if old_comments != task.comments_by_assignee:
                ActivityLog.objects.create(
                    action='comment_added',
                    user=request.user,
                    task=task,
                    description=f"Comment added or updated by assignee: {task.comments_by_assignee}"
                )

            return redirect('task_detail', task_id=task.task_id)
    else:
        form = TaskStatusUpdateForm(instance=task)

    return render(request, 'tasks/update_task_status.html', {'task': task, 'form': form})




@login_required
def send_deadline_reminders(request):
    send_deadline_reminders_logic()
    return HttpResponse("Deadline reminders sent!")

@login_required
def notify_overdue_tasks(request):
    notify_overdue_tasks_logic()
    return HttpResponse("Overdue notifications sent!")

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
    old_assignee = task.assigned_to  # Capture the current assignee before reassigning

    if task.assigned_to != request.user:
        raise PermissionDenied("Only the assignee can reassign the task back to the creator.")

    task.assigned_to = task.assigned_by
    task.save()

    # Log the reassignment
    ActivityLog.objects.create(
        action='assigned',
        user=request.user,
        task=task,
        description=f"Task reassigned from {old_assignee.username} to {task.assigned_to.username}"
    )

    return redirect('assigned_to_me')

@login_required
def dashboard(request):
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.category == 'Task Management System Manager':
        return redirect('activity')  # Redirect Managers to Activity Page
    elif user_profile.category == 'Departmental Manager':
        return redirect('home')      # Redirect Departmental Managers to Home Page
    else:
        return redirect('assigned_to_me')  # Redirect others to Assigned To Me Page

@login_required
def activity(request):
    # Fetch all activity logs for display, ordered by timestamp
    activity_logs = ActivityLog.objects.all().order_by('-timestamp')
    
    return render(request, 'tasks/activity.html', {
        'activity_logs': activity_logs
    })



@login_required
def download_activity_log(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="activity_log.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['User', 'Action', 'Task ID', 'Description', 'Timestamp'])
    
    logs = ActivityLog.objects.all().order_by('-timestamp')
    for log in logs:
        writer.writerow([log.user.username, log.get_action_display(), log.task.task_id, log.description, log.timestamp])
    
    return response

@login_required
def metrics(request):
    # Fetch metrics data based on department and time frame
    now = timezone.now()
    last_24_hours = now - timezone.timedelta(hours=24)

    metrics_data = Task.objects.filter(assigned_date__gte=last_24_hours).values(
    'department__name'
    ).annotate(
        tickets_raised=Count('id'),
        tickets_received=Count('id', filter=Q(status__in=['In Progress', 'Not Started'])),  # Adjust based on 'received' criteria
        tickets_closed=Count('id', filter=Q(status='Completed')),
        tickets_cancelled=Count('id', filter=Q(status='Cancelled')),
    ).order_by('department__name')

    # Calculate open tickets as specified
    for data in metrics_data:
        data['open_tickets'] = data['tickets_raised'] + data['tickets_received'] - data['tickets_closed'] - data['tickets_cancelled']

    # Total row for the table
    total_raised = sum(d.get('tickets_raised', 0) for d in metrics_data)
    total_received = sum(d.get('tickets_received', 0) for d in metrics_data)
    total_closed = sum(d.get('tickets_closed', 0) for d in metrics_data)
    total_cancelled = sum(d.get('tickets_cancelled', 0) for d in metrics_data)
    total_open = sum(d.get('open_tickets', 0) for d in metrics_data)
    
    metrics_summary = {
        'total_raised': total_raised,
        'total_received': total_received,
        'total_closed': total_closed,
        'total_open': total_open,
    }

    # Return metrics data to the template
    return render(request, 'tasks/metrics.html', {
        'metrics_data': metrics_data,
        'metrics_summary': metrics_summary,
    })

# Download metrics as a CSV file
@login_required
def download_metrics(request):
    # Prepare data for CSV download
    now = timezone.now()
    last_24_hours = now - timezone.timedelta(hours=24)

    metrics_data = Task.objects.filter(assigned_date__gte=last_24_hours).values(
        'department__name'
    ).annotate(
        tickets_raised=Count('id'),
        tickets_received=Count('id'),
        tickets_closed=Count('id', filter=Q(status='Completed')),
        open_tickets=Count('id', filter=Q(status='Open'))
    ).order_by('department__name')

    df = pd.DataFrame(metrics_data)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="metrics.csv"'
    df.to_csv(path_or_buf=response, index=False)

    return response

@login_required
def reassign_within_department(request, task_id):
    task = get_object_or_404(Task, task_id=task_id)
    user_profile = UserProfile.objects.get(user=request.user)

    # Ensure only Departmental Managers can access this functionality
    if user_profile.category != 'Departmental Manager':
        raise PermissionDenied("Only Departmental Managers can reassign tasks.")

    # Fetch non-management users in the same department
    non_management_users = UserProfile.objects.filter(
        department=user_profile.department,
        category='Non-Management'
    )

    if request.method == 'POST':
        new_assignee_id = request.POST.get('assigned_to')
        if new_assignee_id:
            new_assignee = get_object_or_404(User, id=new_assignee_id)
            task.assigned_to = new_assignee
            task.save()

            # Log the reassignment action
            ActivityLog.objects.create(
                action='assigned',
                user=request.user,
                task=task,
                description=f"Task {task.task_id} reassigned from {request.user.username} to {new_assignee.username}"
            )
            return redirect('task_detail', task_id=task.task_id)

    return render(request, 'tasks/reassign_within_department.html', {
        'task': task,
        'non_management_users': non_management_users,
    })


