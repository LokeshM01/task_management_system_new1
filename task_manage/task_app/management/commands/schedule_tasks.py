from django_celery_beat.models import PeriodicTask, IntervalSchedule
from datetime import timedelta
from django.utils.timezone import now

def schedule_periodic_tasks():
    # Create schedule (every day at 00:05 AM)
    schedule, created = IntervalSchedule.objects.get_or_create(
        every=1,
        period=IntervalSchedule.DAYS
    )

    # Create Periodic Tasks for sending reminders and overdue notifications
    PeriodicTask.objects.create(
        interval=schedule,
        name='Send Deadline Reminders',
        task='task_app.tasks.send_deadline_reminders_task',
        start_time=now().replace(hour=0, minute=5, second=0, microsecond=0),
    )

    PeriodicTask.objects.create(
        interval=schedule,
        name='Notify Overdue Tasks',
        task='task_app.tasks.notify_overdue_tasks_task',
        start_time=now().replace(hour=0, minute=5, second=0, microsecond=0),
    )
