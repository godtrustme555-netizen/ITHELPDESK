from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime


def ticket_attachment_path(instance, filename):
    return f"ticket_attachments/{instance.ticket_id}/{filename}"

class Ticket(models.Model):
    ticket_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    subject = models.CharField(max_length=200)
    description = models.TextField()

    CATEGORY_CHOICES = [
        ('Hardware', 'Hardware'),
        ('Software', 'Software'),
        ('Network', 'Network'),
        ('Printer', 'Printer'),
        ('Email', 'Email'),
        ('SAP MM', 'SAP MM'),
        ('SAP PP', 'SAP PP'),
        ('SAP FI', 'SAP FI'),
        ('SAP SD', 'SAP SD'),
        ('Access Request', 'Access Request'),
    ]

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Software')
    
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]

    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES)

    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('In Progress', 'In Progress'),
        ('Resolved', 'Resolved'),
        ('Closed', 'Closed'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_tickets', null=True, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='assigned_tickets', null=True, blank=True)

    @property
    def sla_duration(self):
        if self.priority == 'Critical':
            return datetime.timedelta(hours=4)
        elif self.priority == 'High':
            return datetime.timedelta(hours=8)
        elif self.priority == 'Medium':
            return datetime.timedelta(hours=24)
        else:  # Low
            return datetime.timedelta(hours=48)

    @property
    def sla_deadline(self):
        if not self.created_at:
            return None
        return self.created_at + self.sla_duration

    @property
    def is_sla_breached(self):
        deadline = self.sla_deadline
        if not deadline:
            return False
        
        end_time = self.resolved_at if self.status in ['Resolved', 'Closed'] else timezone.now()
        if end_time is None:
            end_time = timezone.now()
        return end_time > deadline

    @property
    def sla_remaining_time_display(self):
        deadline = self.sla_deadline
        if not deadline:
            return "N/A"
        
        is_resolved = self.status in ['Resolved', 'Closed']
        end_time = self.resolved_at if is_resolved else timezone.now()
        if end_time is None:
            end_time = timezone.now()
        
        if end_time > deadline:
            diff = end_time - deadline
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            if is_resolved:
                return f"Breached by {hours}h {minutes}m"
            else:
                return f"{hours}h {minutes}m breached"
        else:
            diff = deadline - end_time
            hours, remainder = divmod(int(diff.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            if is_resolved:
                return "Met"
            else:
                return f"{hours}h {minutes}m remaining"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        # Track status changes to update resolved_at
        if not is_new:
            try:
                original = Ticket.objects.get(pk=self.pk)
                if self.status in ['Resolved', 'Closed'] and original.status not in ['Resolved', 'Closed']:
                    self.resolved_at = timezone.now()
                elif self.status not in ['Resolved', 'Closed'] and original.status in ['Resolved', 'Closed']:
                    self.resolved_at = None
            except Ticket.DoesNotExist:
                pass
        else:
            if self.status in ['Resolved', 'Closed']:
                self.resolved_at = timezone.now()

        super().save(*args, **kwargs)

        # Generate ticket number if not present
        if is_new or not self.ticket_number:
            year = self.created_at.year if self.created_at else timezone.now().year
            prefix = f"IT-{year}-"
            latest = Ticket.objects.filter(ticket_number__startswith=prefix).order_by('-ticket_number').first()
            if latest and latest.ticket_number:
                try:
                    last_num = int(latest.ticket_number.split('-')[-1])
                    next_num = last_num + 1
                except ValueError:
                    next_num = 1
            else:
                next_num = 1
            self.ticket_number = f"{prefix}{next_num:04d}"
            # Use update to avoid infinite recursion and triggering pre/post save signals
            Ticket.objects.filter(pk=self.pk).update(ticket_number=self.ticket_number)

    def __str__(self):
        return self.subject

class Comment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.author.username} on Ticket #{self.ticket.id}"


class TicketAttachment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='attachments')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ticket_attachments')
    file = models.FileField(upload_to=ticket_attachment_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @property
    def filename(self):
        return self.file.name.rsplit('/', 1)[-1]

    def __str__(self):
        return f"{self.filename} on Ticket #{self.ticket_id}"


class TicketActivity(models.Model):
    class EventType(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        COMMENT = 'COMMENT', 'Comment'
        ATTACHMENT = 'ATTACHMENT', 'Attachment'
        STATUS = 'STATUS', 'Status change'
        ASSIGNMENT = 'ASSIGNMENT', 'Assignment'
        UPDATE = 'UPDATE', 'Update'

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='activities')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'ticket activities'

    def __str__(self):
        return f"Ticket #{self.ticket_id}: {self.message}"

