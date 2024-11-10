from django.db import models
from django.contrib.auth.models import User
import random
import string

class Department(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class UserProfile(models.Model):
    USER_CATEGORIES = [
        ('Executive Management', 'Executive Management'),
        ('Departmental Manager', 'Departmental Manager'),
        ('Non-Management', 'Non-Management'),
        ('Task Management System Manager', 'Task Management System Manager'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    category = models.CharField(max_length=50, choices=USER_CATEGORIES)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    reports_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reports')

    def __str__(self):
        return self.user.username

class Task(models.Model):
    STATUS_CHOICES = [
        ('Not Started', 'Not Started'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Stalled', 'Stalled'),
        ('On-Hold', 'On-Hold'),
        ('Cancelled', 'Cancelled'),
    ]

    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ]

    FUNCTIONAL_CATEGORIES = [
        ('Bug Fixing - Live', 'Bug Fixing - Live'),
        ('Bug Fixing - Staging', 'Bug Fixing - Staging'),
        ('Hardware', 'Hardware'),
        ('Issues', 'Issues'),
        ('New Engineering Requirement', 'New Engineering Requirement'),
        ('Others', 'Others'),
        ('Publishing', 'Publishing'),
        ('Research', 'Research'),
        ('Sales', 'Sales'),
        ('Service', 'Service'),
        ('Testing', 'Testing'),
    ]

    # Fields for the Task model
    task_id = models.CharField(max_length=15, unique=True, editable=False)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tasks_assigned')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tasks_received')
    assigned_date = models.DateTimeField(auto_now_add=True)
    deadline = models.DateField()  # Ensure this field is included
    ticket_type = models.CharField(max_length=100, choices=FUNCTIONAL_CATEGORIES)
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Not Started')
    subject = models.CharField(max_length=255)
    request_details = models.TextField(blank=True, null=True)  # Previously comments_by_manager
    attach_file = models.FileField(upload_to='attachments/', blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.task_id:
            self.task_id = self.generate_task_id()
        super(Task, self).save(*args, **kwargs)

    def generate_task_id(self):
        prefix = ''
        if self.department:
            prefix = self.department.name[:3].upper()
        random_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"{prefix}-{random_code}"

    def __str__(self):
        return self.task_id
