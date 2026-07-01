from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Asset(models.Model):
    ASSET_TYPE_CHOICES = [
        ('Laptop', 'Laptop'),
        ('Desktop', 'Desktop'),
        ('Printer', 'Printer'),
        ('Monitor', 'Monitor'),
        ('Scanner', 'Scanner'),
        ('Router', 'Router'),
        ('Switch', 'Switch'),
        ('Server', 'Server'),
        ('UPS', 'UPS'),
        ('Other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('Available', 'Available'),
        ('Assigned', 'Assigned'),
        ('Repair', 'Repair'),
        ('Scrap', 'Scrap'),
        ('Lost', 'Lost'),
    ]

    asset_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    asset_type = models.CharField(max_length=50, choices=ASSET_TYPE_CHOICES)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100, unique=True)
    purchase_date = models.DateField()
    warranty_expiry = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Available')
    location = models.CharField(max_length=100, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.asset_id:
            prefix = "AST-"
            latest = Asset.objects.filter(asset_id__startswith=prefix).order_by('-asset_id').first()
            if latest and latest.asset_id:
                try:
                    last_num = int(latest.asset_id.split('-')[-1])
                    next_num = last_num + 1
                except ValueError:
                    next_num = 1
            else:
                next_num = 1
            self.asset_id = f"{prefix}{next_num:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.brand} {self.model} ({self.asset_id})"


class AssetAssignment(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='assignments')
    employee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_assets')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_assignments')
    assigned_date = models.DateTimeField(default=timezone.now)
    return_date = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        assignee = self.employee.username if self.employee else "Unassigned"
        return f"Assignment of {self.asset.asset_id} to {assignee}"


class AssetActivity(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='activities')
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    notes = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        actor_name = self.actor.username if self.actor else "System"
        return f"{self.asset.asset_id} - {self.action} by {actor_name}"
