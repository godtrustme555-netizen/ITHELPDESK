from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from accounts.models import UserProfile
from .models import SelfCall, SelfCallComment, SelfCallAttachment, SelfCallActivity
from django.utils import timezone
import datetime


class SelfCallModuleTests(TestCase):
    def setUp(self):
        # Create users with different roles
        self.admin_user = User.objects.create_user(username='admin_user', password='password123', email='admin@example.com')
        admin_profile = self.admin_user.profile
        admin_profile.role = UserProfile.Role.ADMIN
        admin_profile.save()
        
        self.support_user = User.objects.create_user(username='support_user', password='password123', email='support@example.com')
        support_profile = self.support_user.profile
        support_profile.role = UserProfile.Role.IT_SUPPORT
        support_profile.save()

        self.employee_user = User.objects.create_user(username='employee_user', password='password123', email='emp@example.com')
        employee_profile = self.employee_user.profile
        employee_profile.role = UserProfile.Role.EMPLOYEE
        employee_profile.save()

        # Clients for request tests
        self.admin_client = Client()
        self.admin_client.login(username='admin_user', password='password123')

        self.support_client = Client()
        self.support_client.login(username='support_user', password='password123')

        self.employee_client = Client()
        self.employee_client.login(username='employee_user', password='password123')

    def test_employee_cannot_access_self_calls(self):
        dashboard_url = reverse('self_call_dashboard')
        response = self.employee_client.get(dashboard_url)
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_support_can_access_self_calls(self):
        dashboard_url = reverse('self_call_dashboard')
        response = self.support_client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_self_call_creation_generates_id(self):
        # Create a self call
        sc = SelfCall.objects.create(
            title='Daily Server Check',
            description='Check DC logs',
            category='Server',
            priority='High',
            status='Open',
            department='IT Infrastructure',
            created_by=self.support_user
        )
        self.assertIsNotNone(sc.self_call_id)
        self.assertTrue(sc.self_call_id.startswith(f"SC-{timezone.now().year}-"))
        self.assertEqual(sc.self_call_id[-4:], "0001")

    def test_self_call_comments_and_activities(self):
        # Create self call
        sc = SelfCall.objects.create(
            title='Firewall Update',
            description='Close unused ports',
            category='Firewall',
            priority='Critical',
            status='Open',
            department='Security',
            created_by=self.support_user
        )
        
        # Add comment
        comment = SelfCallComment.objects.create(
            self_call=sc,
            author=self.support_user,
            text='Updated incoming rules'
        )
        
        # Test activity log creation
        act = SelfCallActivity.objects.create(
            self_call=sc,
            actor=self.support_user,
            event_type=SelfCallActivity.EventType.COMMENT,
            message='Added rule change notes'
        )

        self.assertEqual(sc.comments.count(), 1)
        self.assertEqual(sc.activities.count(), 1)
        self.assertEqual(sc.comments.first().text, 'Updated incoming rules')

    def test_sla_breach_calculation(self):
        sc = SelfCall.objects.create(
            title='CCTV System Maintenance',
            description='Replace main cameras',
            category='CCTV',
            priority='Critical',
            status='Open',
            department='Security',
            created_by=self.support_user
        )
        
        # Mock created_date to be 10 hours ago to trigger SLA breach (Critical SLA is 4 hours)
        sc.created_date = timezone.now() - datetime.timedelta(hours=10)
        sc.save()

        self.assertTrue(sc.is_sla_breached)
        self.assertIn("breached", sc.sla_remaining_time_display)

    def test_exports_endpoints(self):
        sc = SelfCall.objects.create(
            title='Switch Config Backup',
            description='Save core switches running-config to NAS',
            category='Switch',
            priority='Medium',
            status='Open',
            department='Network',
            created_by=self.support_user
        )
        
        export_url = reverse('export_self_calls')
        
        # Test CSV export
        response = self.support_client.get(f"{export_url}?format=csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

        # Test Excel export
        response = self.support_client.get(f"{export_url}?format=excel")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.ms-excel')

        # Test PDF template trigger
        response = self.support_client.get(f"{export_url}?format=pdf")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "window.print()")
