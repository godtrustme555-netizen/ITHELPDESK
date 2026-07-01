from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime


def self_call_attachment_path(instance, filename):
    return f"self_call_attachments/{instance.self_call_id}/{filename}"


class SelfCall(models.Model):
    CATEGORY_CHOICES = [
        ('Server', 'Server'),
        ('Network', 'Network'),
        ('Firewall', 'Firewall'),
        ('Switch', 'Switch'),
        ('Router', 'Router'),
        ('WiFi', 'WiFi'),
        ('CCTV', 'CCTV'),
        ('SAP', 'SAP'),
        ('ERP', 'ERP'),
        ('Windows', 'Windows'),
        ('Linux', 'Linux'),
        ('Virtualization', 'Virtualization'),
        ('VMware', 'VMware'),
        ('Backup', 'Backup'),
        ('NAS', 'NAS'),
        ('Storage', 'Storage'),
        ('Email', 'Email'),
        ('Office 365', 'Office 365'),
        ('Azure', 'Azure'),
        ('AWS', 'AWS'),
        ('Database', 'Database'),
        ('Printer', 'Printer'),
        ('Security', 'Security'),
        ('Patch Management', 'Patch Management'),
        ('Hardware', 'Hardware'),
        ('Software', 'Software'),
        ('Other', 'Other'),
    ]

    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]

    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Assigned', 'Assigned'),
        ('In Progress', 'In Progress'),
        ('Pending', 'Pending'),
        ('Completed', 'Completed'),
        ('Closed', 'Closed'),
        ('Cancelled', 'Cancelled'),
    ]

    DEPARTMENT_CHOICES = [
        ('IT Infrastructure', 'IT Infrastructure'),
        ('Network', 'Network'),
        ('SAP', 'SAP'),
        ('Security', 'Security'),
        ('Support', 'Support'),
        ('Administration', 'Administration'),
    ]

    self_call_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    department = models.CharField(max_length=50, choices=DEPARTMENT_CHOICES)
    
    assigned_engineer = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='assigned_self_calls', null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_self_calls')
    
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    planned_date = models.DateTimeField(null=True, blank=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    
    sla_enabled = models.BooleanField(default=True, verbose_name="Enable SLA Tracking")

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
        if not self.created_date:
            return None
        return self.created_date + self.sla_duration

    @property
    def is_sla_breached(self):
        if not self.sla_enabled:
            return False
        deadline = self.sla_deadline
        if not deadline:
            return False
        
        end_time = self.completed_date if self.status in ['Completed', 'Closed'] else timezone.now()
        if end_time is None:
            end_time = timezone.now()
        return end_time > deadline

    @property
    def sla_remaining_time_display(self):
        if not self.sla_enabled:
            return "Disabled"
        deadline = self.sla_deadline
        if not deadline:
            return "N/A"
        
        is_resolved = self.status in ['Completed', 'Closed']
        end_time = self.completed_date if is_resolved else timezone.now()
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
        
        # Track status changes to update completed_date
        if not is_new:
            try:
                original = SelfCall.objects.get(pk=self.pk)
                if self.status in ['Completed', 'Closed'] and original.status not in ['Completed', 'Closed']:
                    self.completed_date = timezone.now()
                elif self.status not in ['Completed', 'Closed'] and original.status in ['Completed', 'Closed']:
                    self.completed_date = None
            except SelfCall.DoesNotExist:
                pass
        else:
            if self.status in ['Completed', 'Closed']:
                self.completed_date = timezone.now()

        super().save(*args, **kwargs)

        # Generate Self Call ID if not present
        if is_new or not self.self_call_id:
            year = self.created_date.year if self.created_date else timezone.now().year
            prefix = f"SC-{year}-"
            latest = SelfCall.objects.filter(self_call_id__startswith=prefix).order_by('-self_call_id').first()
            if latest and latest.self_call_id:
                try:
                    last_num = int(latest.self_call_id.split('-')[-1])
                    next_num = last_num + 1
                except ValueError:
                    next_num = 1
            else:
                next_num = 1
            self.self_call_id = f"{prefix}{next_num:04d}"
            # Use update to avoid infinite recursion
            SelfCall.objects.filter(pk=self.pk).update(self_call_id=self.self_call_id)

    def __str__(self):
        return f"{self.self_call_id or 'SC-NEW'} - {self.title}"


class SelfCallComment(models.Model):
    self_call = models.ForeignKey(SelfCall, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.author.username} on SC #{self.self_call_id}"


class SelfCallAttachment(models.Model):
    self_call = models.ForeignKey(SelfCall, on_delete=models.CASCADE, related_name='attachments')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='self_call_attachments')
    file = models.FileField(upload_to=self_call_attachment_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @property
    def filename(self):
        return self.file.name.rsplit('/', 1)[-1]

    def __str__(self):
        return f"{self.filename} on SC #{self.self_call_id}"


class SelfCallActivity(models.Model):
    class EventType(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        ASSIGNED = 'ASSIGNED', 'Assigned'
        STATUS = 'STATUS', 'Status Changed'
        COMMENT = 'COMMENT', 'Comment Added'
        ATTACHMENT = 'ATTACHMENT', 'Attachment Uploaded'
        CLOSED = 'CLOSED', 'Closed'
        UPDATE = 'UPDATE', 'Details Updated'

    self_call = models.ForeignKey(SelfCall, on_delete=models.CASCADE, related_name='activities')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'self call activities'

    def __str__(self):
        return f"SC #{self.self_call_id}: {self.message}"
