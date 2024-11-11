# task_app/utils.py
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings

def send_notification_email(to_email, template_name, context):
    subject = context.get('subject', 'Notification')
    message = render_to_string(template_name, context)
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [to_email],
        html_message=message,
    )
