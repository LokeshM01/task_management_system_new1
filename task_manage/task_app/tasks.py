from django.utils.timezone import now
from datetime import timedelta
from .models import Task, User
from django.core.mail import send_mail
from django.template.loader import render_to_string

def send_deadline_reminders_logic():
    # Fetch tasks with deadlines within the next 24 hours
    upcoming_deadline = now() + timedelta(hours=24)
    tasks = Task.objects.filter(deadline__lte=upcoming_deadline, status__in=['Not Started', 'In Progress'])

    for task in tasks:
        if task.assigned_to.email:  # Check if the assigned user has an email
            # Prepare email context
            context = {
                'task': task,
            }
            email_body = render_to_string('emails/reminder.html', context)
            send_mail(
                f"Reminder: Task {task.task_id} deadline approaching",
                '',  # Empty plain text body
                'no-reply@yourdomain.com',
                [task.assigned_to.email],
                html_message=email_body,
            )

def notify_overdue_tasks_logic():
    # Fetch overdue tasks
    overdue_tasks = Task.objects.filter(deadline__lt=now(), status__in=['Not Started', 'In Progress'])

    for task in overdue_tasks:
        if task.assigned_by.email:  # Check if the creator has an email
            # Prepare email context
            context = {
                'task': task,
            }
            email_body = render_to_string('emails/overdue_notification.html', context)
            send_mail(
                f"Overdue Task: {task.task_id}",
                '',  # Empty plain text body
                'no-reply@yourdomain.com',
                [task.assigned_by.email],
                html_message=email_body,
            )
