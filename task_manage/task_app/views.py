from django.shortcuts import render, redirect, get_object_or_404
from .models import Task, UserProfile, Department
from django.contrib.auth.decorators import login_required
from .forms import TaskForm
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q,F
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
from datetime import date

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
    today = date.today()
    if user_profile.category == 'Departmental Manager':
        # Fetch all tasks related to the department of the manager
        department = user_profile.department
        tasks = Task.objects.filter(
            # Tasks created by members of the manager's department
            Q(assigned_by__userprofile__department=department) |
            # Tasks assigned to members of the manager's department
            Q(assigned_to__userprofile__department=department)|
            Q(department__name=department),

            assigned_date__lte=today
        ).order_by('-assigned_date')
        return render(request, 'tasks/home.html', {
            'tasks': tasks,
            'departments': Department.objects.all(),
            'users':User.objects.all(),
        })

    return redirect('assigned_to_me')

@login_required
def assigned_to_me(request):
    today = date.today()
    # Filter tasks where the assigned_to field matches the current user
    tasks = Task.objects.filter(assigned_to=request.user, assigned_date__lte=today).order_by('-assigned_date')

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
    today = date.today()
    tasks = Task.objects.filter(assigned_by=request.user, assigned_date__lte=today).order_by('-assigned_date')
    # Fetch tasks where the logged-in user is the assigner
    # tasks = Task.objects.filter(assigned_by=request.user)

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
            task.assigned_date = date.today()
            task.save()

            # Notify the departmental manager (if exists)
            if task.department and hasattr(task.department, 'manager') and task.department.manager:
                manager_email = task.department.manager.email  # Ensure the manager's email exists
                view_ticket_url = request.build_absolute_uri(f'/tasks/detail/{task.task_id}/')
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
                view_ticket_url = request.build_absolute_uri(f'/tasks/detail/{task.task_id}/')
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
            view_ticket_url = request.build_absolute_uri(f'/tasks/detail/{task.task_id}/')
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
    user_profile = UserProfile.objects.get(user=request.user)
    if task.assigned_by != request.user and not (
    user_profile.category == 'Departmental Manager' and
    task.assigned_by.userprofile.department == user_profile.department
    ):
        raise PermissionDenied

    old_priority = task.priority  # Capture the current priority before changes
    old_status = task.status

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, instance=task, user=request.user)
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
            if old_priority != updated_task.priority:
                ActivityLog.objects.create(
                    action='priority_changed',
                    user=request.user,
                    task=task,
                    description=f"Priority changed from {old_priority} to {updated_task.priority}"
                )

            return redirect('assigned_by_me')
        else:
            print("Form errors:", form.errors)  # Print form errors if the form is not valid
    else:
        form = TaskForm(instance=task, user=request.user)

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
    initial_deadline=task.deadline
    if request.method == 'POST':
        form = TaskStatusUpdateForm(request.POST, instance=task)
        if form.is_valid():
            form.save()

            view_ticket_url = request.build_absolute_uri(f'/tasks/detail/{task.task_id}/')
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
                    description=f"Deadline revised from {initial_deadline} to {task.revised_completion_date}"
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
    user_profile = UserProfile.objects.get(user=request.user)
    if task.assigned_to != request.user and not (
    user_profile.category == 'Departmental Manager' and
    task.assigned_to.userprofile.department == user_profile.department
    ):
        raise PermissionDenied

    

    # Redirect to a new page where user can add a note
    return redirect('task_note_page', task_id=task.task_id)  # Assuming 'task_note_page' is the new view for adding notes


@login_required
def task_note_page(request, task_id):
    task = get_object_or_404(Task, task_id=task_id)
    old_assignee = task.assigned_to
    user_profile = UserProfile.objects.get(user=request.user)
    if task.assigned_to != request.user and not (
    user_profile.category == 'Departmental Manager' and
    task.assigned_to.userprofile.department == user_profile.department
    ):
        raise PermissionDenied

    # Handle note addition and file attachment by assignee
    if request.method == 'POST':
        note = request.POST.get('note')
        task.notes = note
        from_dept = task.assigned_by.userprofile.department

        # Handle the file attachment by assignee
        attachment = request.FILES.get('attachment_by_assignee')
        if attachment:
            task.attachment_by_assignee = attachment

        task.assigned_to = task.assigned_by
        task.department = from_dept
        task.save()

        # Log the reassignment
        ActivityLog.objects.create(
            action='reassigned',
            user=request.user,
            task=task,
            description=f"Task reassigned from {old_assignee.username} to {task.assigned_to.username}"
        )

        # Log the note addition
        ActivityLog.objects.create(
            action='comment_added',
            user=request.user,
            task=task,
            description=f"Note added by {request.user.username}: {note}"
        )

        return redirect('task_detail', task_id=task.task_id)

    return render(request, 'tasks/task_note_page.html', {'task': task})


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

from django.db.models import F, Q, Count

@login_required
def metrics(request):
    # Get the current time and the last 24 hours time
    now = timezone.now()
    last_24_hours = now - timezone.timedelta(hours=24)
    today_date = date.today()
    seventy_two_hours = now - timedelta(hours=72)

    # Metrics for Last 24 Hours (raised and received)
    metrics_data = Task.objects.values('department__name').annotate(
        tickets_received_last_24hr=Count('id', filter=Q(department__name=F('department__name'), assigned_date__gte=last_24_hours, assigned_date__lte=today_date)),
        open_tickets_received=Count('id', filter=Q(department__name=F('department__name'), status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'], assigned_date__lte=today_date)),
    ).order_by('department__name')

    # Add all-time data for raised and received tickets
    total_tickets_passed_72_hours = 0
    total_tickets_passed_revised_deadline = 0
    for data in metrics_data:
        department_name = data['department__name']

        tickets_raised_all_time = Task.objects.filter(
            assigned_by__userprofile__department__name=department_name,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
            assigned_date__lte=today_date
        ).count()

        tickets_raised_last_24hr = Task.objects.filter(
            assigned_by__userprofile__department__name=department_name,
            assigned_date__gte=last_24_hours,
            assigned_date__lte=today_date
        ).count()

        data['tickets_raised_last_24hr'] = tickets_raised_last_24hr

        tickets_received_all_time = Task.objects.filter(
            department__name=department_name,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
            assigned_date__lte=today_date
        ).count()

        data['open_tickets_raised'] = tickets_raised_all_time
        data['open_tickets_received'] = tickets_received_all_time
        
        # Tickets passed 72 hours after raising
        passed_72_hours = Task.objects.filter(
            department__name=department_name,
            assigned_date__lte=seventy_two_hours,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
        ).count()
        data['tickets_passed_72_hours'] = passed_72_hours
        total_tickets_passed_72_hours += passed_72_hours
        
        # Tickets passed the revised deadline or original deadline
        passed_revised_deadline = Task.objects.filter(
            department__name=department_name,
            deadline__lte=now,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
        ).count()
        data['tickets_passed_revised_deadline'] = passed_revised_deadline
        total_tickets_passed_revised_deadline += passed_revised_deadline

        # Get older open tickets with task data
        older_open_tickets_data = Task.objects.filter(
            department__name=department_name,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
            assigned_date__lt=last_24_hours
        ).count()
        data['older_open_tickets'] = older_open_tickets_data  # Storing actual task data

    for data in metrics_data:
        department_name = data['department__name']

        all_task_of_this_dept = Task.objects.filter(
            assigned_to__userprofile__department__name=department_name,
            status__in=['In Progress', 'Not Started', 'Pending', 'Processing', 'Delay Processing', 'Waiting for confirmation'],
            assigned_date__lte=today_date
        )

        pending_by_dept = {}

        for task in all_task_of_this_dept:
            assignor_dept_name = task.assigned_by.userprofile.department.name

            if assignor_dept_name not in pending_by_dept:
                pending_by_dept[assignor_dept_name] = 0
            pending_by_dept[assignor_dept_name] += 1

        data['pending_tickets_bifurcation'] = pending_by_dept

    # Total row for the last 24 hours
    total_raised_last_24hr = sum(d.get('tickets_raised_last_24hr', 0) for d in metrics_data)
    total_received_last_24hr = sum(d.get('tickets_received_last_24hr', 0) for d in metrics_data)
    total_open_raised = sum(d.get('open_tickets_raised', 0) for d in metrics_data)
    total_open_received = sum(d.get('open_tickets_received', 0) for d in metrics_data)
    total_older_open_tickets = sum(d.get('older_open_tickets', []) for d in metrics_data)

    total_pending_tickets = 0
    for department in metrics_data:
        pending_bifurcation = department.get('pending_tickets_bifurcation', {})
        total_pending_tickets += sum(pending_bifurcation.values())

    metrics_summary = {
        'total_raised_last_24hr': total_raised_last_24hr,
        'total_received_last_24hr': total_received_last_24hr,
        'total_open_raised': total_open_raised,
        'total_open_received': total_open_received,
        'total_older_open_tickets': total_older_open_tickets,
        'total_pending_tickets': total_pending_tickets,
        'total_tickets_passed_72_hours': total_tickets_passed_72_hours,  # Include total passed 72 hours in the summary
        'total_tickets_passed_revised_deadline': total_tickets_passed_revised_deadline,  # Include total passed revised deadline in the summary
    }

    return render(request, 'tasks/metrics.html', {
        'metrics_data': metrics_data,
        'metrics_summary': metrics_summary,
    })

    





# Download metrics as a CSV file

@login_required
def download_metrics(request):
    # Get the current time and the last 24 hours time
    now = timezone.now()
    last_24_hours = now - timezone.timedelta(hours=24)
    today_date = date.today()
    seventy_two_hours = now - timedelta(hours=72)

    # Metrics for Last 24 Hours (raised and received)
    metrics_data = Task.objects.values('department__name').annotate(
        tickets_received_last_24hr=Count('id', filter=Q(assigned_to__userprofile__department__name=F('department__name'), assigned_date__gte=last_24_hours, assigned_date__lte=today_date)),
        open_tickets_received=Count('id', filter=Q(assigned_to__userprofile__department__name=F('department__name'), status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'], assigned_date__lte=today_date)),
    ).order_by('department__name')

    # Add all-time data for raised and received tickets
    for data in metrics_data:
        department_name = data['department__name']

        tickets_raised_all_time = Task.objects.filter(
            assigned_by__userprofile__department__name=department_name,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
            assigned_date__lte=today_date
        ).count()

        tickets_raised_last_24hr = Task.objects.filter(
            assigned_by__userprofile__department__name=department_name,
            assigned_date__gte=last_24_hours,
            assigned_date__lte=today_date
        ).count()

        data['tickets_raised_last_24hr'] = tickets_raised_last_24hr

        tickets_received_all_time = Task.objects.filter(
            assigned_to__userprofile__department__name=department_name,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
            assigned_date__lte=today_date
        ).count()

        data['open_tickets_raised'] = tickets_raised_all_time
        data['open_tickets_received'] = tickets_received_all_time

        # Tickets passed 72 hours after raising
        passed_72_hours = Task.objects.filter(
            department__name=department_name,
            assigned_date__lte=seventy_two_hours,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
        ).count()
        data['tickets_passed_72_hours'] = passed_72_hours
        
        # Tickets passed the revised deadline or original deadline
        passed_revised_deadline = Task.objects.filter(
            department__name=department_name,
            deadline__lte=now,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
        ).count()
        data['tickets_passed_revised_deadline'] = passed_revised_deadline

        # Get older open tickets with task data
        older_open_tickets_data = Task.objects.filter(
            assigned_to__userprofile__department__name=department_name,
            status__in=['In Progress', 'Not Started', 'Waiting for confirmation', 'Pending', 'Delay processing', 'Processing'],
            assigned_date__lt=last_24_hours
        )
        data['older_open_tickets'] = older_open_tickets_data  # Storing actual task data

    # Add Pending Tickets by Department (Bifurcation)
    for data in metrics_data:
        department_name = data['department__name']

        # Filter tasks where assigned_to department matches the current department
        all_task_of_this_dept = Task.objects.filter(
            assigned_to__userprofile__department__name=department_name,
            status__in=['In Progress', 'Not Started', 'Pending', 'Processing', 'Delay Processing', 'Waiting for confirmation'],
            assigned_date__lt=last_24_hours
        )

        # Create a map to store pending tickets count by assigned_by department
        pending_by_dept = {}

        # Loop through tasks and populate pending_by_dept map
        for task in all_task_of_this_dept:
            assignor_dept_name = task.assigned_by.userprofile.department.name  # Updated variable name

            # Increment the pending ticket count for the assignor department
            if assignor_dept_name not in pending_by_dept:
                pending_by_dept[assignor_dept_name] = 0
            pending_by_dept[assignor_dept_name] += 1

        # Set the pending_by_dept map as the bifurcation value
        data['pending_tickets_bifurcation'] = pending_by_dept

    # Prepare CSV Response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="metrics_data.csv"'

    writer = csv.writer(response)

    # Writing the header row
    writer.writerow([
        'Department Name',
        'Tickets Received Last 24hr',
        'Open Tickets Received',
        'Tickets Raised Last 24hr',
        'Open Tickets Raised',
        'Older Open Tickets',
        'Pending Tickets Bifurcation',
        'Tickets Passed 72 Hours After Raising',  # New Column Header
        'Tickets Passed the Revised Deadline'   # New Column Header
    ])

    # Writing data rows
    for data in metrics_data:
        department_name = data['department__name']
        tickets_received_last_24hr = data['tickets_received_last_24hr']
        open_tickets_received = data['open_tickets_received']
        tickets_raised_last_24hr = data['tickets_raised_last_24hr']
        open_tickets_raised = data['open_tickets_raised']
        older_open_tickets = len(data['older_open_tickets'])  # Assuming this is a list of task objects
        pending_tickets_bifurcation = str(data['pending_tickets_bifurcation'])  # Convert to string for CSV format
        tickets_passed_72_hours = data['tickets_passed_72_hours']
        tickets_passed_revised_deadline = data['tickets_passed_revised_deadline']

        writer.writerow([
            department_name,
            tickets_received_last_24hr,
            open_tickets_received,
            tickets_raised_last_24hr,
            open_tickets_raised,
            older_open_tickets,
            pending_tickets_bifurcation,
            tickets_passed_72_hours,  # New Column Data
            tickets_passed_revised_deadline  # New Column Data
        ])

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

            # Notify the assignee (if assigned)
            if task.assigned_to:
                assignee_email = task.assigned_to.email
                view_ticket_url = request.build_absolute_uri(f'/tasks/detail/{task.task_id}/')
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


