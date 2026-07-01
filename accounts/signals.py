from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
import logging

from .models import UserProfile, UserActivityLog

logger = logging.getLogger('security')


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        role = (
            UserProfile.Role.ADMIN
            if instance.is_superuser
            else UserProfile.Role.IT_SUPPORT
            if instance.is_staff
            else UserProfile.Role.EMPLOYEE
        )
        UserProfile.objects.get_or_create(user=instance, defaults={"role": role})


def get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    ip = get_client_ip(request)
    ua = request.META.get('HTTP_USER_AGENT', '') if request else ''
    UserActivityLog.objects.create(
        user=user,
        action="User logged in successfully",
        ip_address=ip,
        user_agent=ua
    )
    logger.info(f"SUCCESSFUL_LOGIN: username={user.username} ip={ip} user_agent={ua}")


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user:
        ip = get_client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '') if request else ''
        UserActivityLog.objects.create(
            user=user,
            action="User logged out",
            ip_address=ip,
            user_agent=ua
        )
        logger.info(f"LOGOUT: username={user.username} ip={ip} user_agent={ua}")


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    ip = get_client_ip(request)
    ua = request.META.get('HTTP_USER_AGENT', '') if request else ''
    username = credentials.get('username', 'Unknown')
    
    UserObj = get_user_model()
    try:
        user = UserObj.objects.get(username=username)
    except UserObj.DoesNotExist:
        user = None

    UserActivityLog.objects.create(
        user=user,
        action=f"Failed login attempt for username: {username}",
        ip_address=ip,
        user_agent=ua
    )
    logger.warning(f"FAILED_LOGIN: username={username} ip={ip} user_agent={ua}")

