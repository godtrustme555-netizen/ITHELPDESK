import os
import logging
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from accounts.models import UserProfile
from .models import SelfCallActivity

logger = logging.getLogger('django')


@receiver(post_save, sender=SelfCallActivity)
def send_self_call_activity_notification(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        activity = instance
        self_call = activity.self_call
        actor = activity.actor
        event_type = activity.event_type
        message = activity.message

        recipients = set()

        # 1. Notify creator if they are not the actor
        if self_call.created_by and self_call.created_by.email and self_call.created_by != actor:
            recipients.add(self_call.created_by.email)

        # 2. Notify assigned engineer if they are not the actor
        if self_call.assigned_engineer and self_call.assigned_engineer.email and self_call.assigned_engineer != actor:
            recipients.add(self_call.assigned_engineer.email)

        # 3. Notify Admins
        admins = User.objects.filter(
            models.Q(is_superuser=True) |
            models.Q(profile__role=UserProfile.Role.ADMIN)
        ).exclude(email='').values_list('email', flat=True).distinct()
        recipients.update(admins)

        # Remove the actor's own email from list of recipients
        if actor and actor.email in recipients:
            recipients.remove(actor.email)

        if not recipients:
            logger.info(f"No email notification recipients found for Self Call #{self_call.id} activity.")
            return

        site_url = os.environ.get('SITE_URL', 'http://localhost:8000')
        self_call_url = f"{site_url.rstrip('/')}/self-calls/{self_call.id}/"
        self_call_ident = self_call.self_call_id if self_call.self_call_id else f"#{self_call.id}"

        # Customize subjects, titles, and messages for specific notifications
        if event_type == SelfCallActivity.EventType.CREATED:
            subject = f"[IT Self Call] Task Created: {self_call_ident} - {self_call.title}"
            email_title = "Self Call Created"
            email_message = f"Self Call {self_call_ident} has been created successfully."
        elif event_type == SelfCallActivity.EventType.ASSIGNED:
            subject = f"[IT Self Call] Task Assigned: {self_call_ident} - {self_call.title}"
            email_title = "Self Call Assigned"
            engineer_name = self_call.assigned_engineer.username if self_call.assigned_engineer else "Unassigned"
            email_message = f"Self Call {self_call_ident} has been assigned to {engineer_name}."
        elif event_type == SelfCallActivity.EventType.STATUS and self_call.status in ['Completed', 'Closed']:
            subject = f"[IT Self Call] Task Completed: {self_call_ident} - {self_call.title}"
            email_title = "Self Call Closed/Completed"
            email_message = f"Self Call {self_call_ident} has been marked as {self_call.status}."
        else:
            subject = f"[IT Self Call] Task {self_call_ident}: {activity.get_event_type_display()} - {self_call.title}"
            email_title = activity.get_event_type_display()
            email_message = message

        context = {
            'self_call': self_call,
            'actor': actor,
            'event_type': event_type,
            'message': message,
            'email_title': email_title,
            'email_message': email_message,
            'self_call_url': self_call_url,
            'site_url': site_url,
        }

        # Render HTML and text templates
        html_content = render_to_string('selfcalls/emails/notification_email.html', context)
        text_content = render_to_string('selfcalls/emails/notification_email.txt', context)

        # Construct and send email
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=list(recipients)
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Notification email sent to {list(recipients)} for Self Call #{self_call.id} activity: '{message}'.")

    except Exception as e:
        logger.error(f"Failed to send email notification for Self Call activity: {str(e)}", exc_info=True)
