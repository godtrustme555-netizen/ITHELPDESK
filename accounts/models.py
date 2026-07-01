from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        IT_SUPPORT = "IT_SUPPORT", "IT Support"
        EMPLOYEE = "EMPLOYEE", "Employee"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


def get_user_role(user):
    """Return a role while remaining compatible with pre-RBAC users."""
    if user.is_superuser:
        return UserProfile.Role.ADMIN
    try:
        return UserProfile.Role(user.profile.role)
    except UserProfile.DoesNotExist:
        return UserProfile.Role.IT_SUPPORT if user.is_staff else UserProfile.Role.EMPLOYEE


def user_is_admin(user):
    return user.is_authenticated and get_user_role(user) == UserProfile.Role.ADMIN


def user_is_it_support(user):
    return user.is_authenticated and get_user_role(user) == UserProfile.Role.IT_SUPPORT


def user_can_manage_tickets(user):
    return user_is_admin(user) or user_is_it_support(user)


class UserActivityLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'user activity log'
        verbose_name_plural = 'user activity logs'

    def __str__(self):
        username = self.user.username if self.user else "Anonymous"
        return f"{username} - {self.action} at {self.timestamp}"

