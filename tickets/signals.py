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
from .models import TicketActivity

logger = logging.getLogger('django')


@receiver(post_save, sender=TicketActivity)
def send_activity_notification(sender, instance, created, **kwargs):
    if not created:
        return

    # We wrap the entire email sending block in a try-except to ensure email issues
    # never block database saves or user transactions (reliability requirement).
    try:
        activity = instance
        ticket = activity.ticket
        actor = activity.actor
        event_type = activity.event_type
        message = activity.message

        recipients = set()

        # 1. Notify creator if they are not the actor
        if ticket.created_by and ticket.created_by.email and ticket.created_by != actor:
            recipients.add(ticket.created_by.email)

        # 2. Notify assignee if they are not the actor
        if ticket.assigned_to and ticket.assigned_to.email and ticket.assigned_to != actor:
            recipients.add(ticket.assigned_to.email)

        # 3. If a ticket is newly created, notify all Admin and IT Support staff
        if event_type == TicketActivity.EventType.CREATED:
            staff_emails = User.objects.filter(
                models.Q(is_superuser=True) |
                models.Q(is_staff=True) |
                models.Q(profile__role__in=[UserProfile.Role.ADMIN, UserProfile.Role.IT_SUPPORT])
            ).exclude(email='').values_list('email', flat=True).distinct()
            recipients.update(staff_emails)

        # Remove the actor's own email from list of recipients
        if actor and actor.email in recipients:
            recipients.remove(actor.email)

        if not recipients:
            logger.info(f"No email notification recipients found for Ticket #{ticket.id} activity.")
            return

        site_url = os.environ.get('SITE_URL', 'http://localhost:8000')
        ticket_url = f"{site_url.rstrip('/')}/ticket/{ticket.id}/"

        ticket_ident = ticket.ticket_number if ticket.ticket_number else f"#{ticket.id}"

        # Customize subjects, titles, and messages for specific notifications
        if event_type == TicketActivity.EventType.CREATED:
            subject = f"[IT Helpdesk] Ticket Created: {ticket_ident} - {ticket.subject}"
            email_title = "Ticket Created"
            email_message = f"Ticket {ticket_ident} has been created successfully."
        elif event_type == TicketActivity.EventType.ASSIGNMENT:
            subject = f"[IT Helpdesk] Ticket Assigned: {ticket_ident} - {ticket.subject}"
            email_title = "Ticket Assigned"
            assignee_name = ticket.assigned_to.username if ticket.assigned_to else "Unassigned"
            email_message = f"Ticket {ticket_ident} has been assigned to {assignee_name}."
        elif event_type == TicketActivity.EventType.STATUS and ticket.status == 'Resolved':
            subject = f"[IT Helpdesk] Ticket Resolved: {ticket_ident} - {ticket.subject}"
            email_title = "Ticket Resolved"
            email_message = f"Ticket {ticket_ident} has been marked as Resolved."
        else:
            subject = f"[IT Helpdesk] Ticket {ticket_ident}: {activity.get_event_type_display()} - {ticket.subject}"
            email_title = activity.get_event_type_display()
            email_message = message

        context = {
            'ticket': ticket,
            'actor': actor,
            'event_type': event_type,
            'message': message,
            'email_title': email_title,
            'email_message': email_message,
            'ticket_url': ticket_url,
            'site_url': site_url,
        }
        
        # Render HTML and text templates
        html_content = render_to_string('tickets/emails/notification_email.html', context)
        text_content = render_to_string('tickets/emails/notification_email.txt', context)

        # Construct and send email
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=list(recipients)
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Notification email sent to {list(recipients)} for Ticket #{ticket.id} activity: '{message}'.")

    except Exception as e:
        logger.error(f"Failed to send email notification for Ticket #{instance.ticket_id} activity: {str(e)}", exc_info=True)
