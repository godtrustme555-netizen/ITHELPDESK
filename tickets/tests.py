from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
import shutil
import tempfile

from accounts.models import UserProfile
from .models import Comment, Ticket, TicketActivity, TicketAttachment


class RoleBasedAccessTests(TestCase):
    def setUp(self):
        self.employee = User.objects.create_user('employee', password='test-pass')
        self.other_employee = User.objects.create_user('other', password='test-pass')
        self.support = User.objects.create_user('support', password='test-pass')
        self.support.profile.role = UserProfile.Role.IT_SUPPORT
        self.support.profile.save()
        self.admin_user = User.objects.create_user('app-admin', password='test-pass')
        self.admin_user.profile.role = UserProfile.Role.ADMIN
        self.admin_user.profile.save()
        self.ticket = Ticket.objects.create(
            subject='Printer issue',
            description='The printer is offline.',
            priority='Medium',
            created_by=self.employee,
        )

    def login(self, user):
        self.client.force_login(user)

    def test_new_users_receive_employee_role(self):
        self.assertEqual(self.employee.profile.role, UserProfile.Role.EMPLOYEE)

    def test_visible_branding_is_consistent_across_pages(self):
        title = '<title>IT HELPDESK</title>'

        response = self.client.get(reverse('login'))
        self.assertContains(response, title, html=True)
        self.assertContains(response, 'IT HELPDESK')
        self.assertContains(response, 'Employee Support Portal')

        self.login(self.employee)
        for url in [
            reverse('home'),
            reverse('create_ticket'),
            reverse('ticket_detail', args=[self.ticket.pk]),
        ]:
            response = self.client.get(url)
            self.assertContains(response, title, html=True)
            self.assertContains(response, 'IT HELPDESK')

        self.client.logout()
        superuser = User.objects.create_superuser(
            'django-admin',
            email='admin@example.com',
            password='test-pass',
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'IT HELPDESK')
        self.assertContains(response, 'Administration')

    def test_employee_sees_only_own_tickets(self):
        Ticket.objects.create(
            subject='Other ticket', description='Private', priority='Low',
            created_by=self.other_employee,
        )
        self.login(self.employee)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Printer issue')
        self.assertNotContains(response, 'Other ticket')

    def test_employee_cannot_view_or_update_another_users_ticket(self):
        self.login(self.other_employee)
        self.assertEqual(
            self.client.get(reverse('ticket_detail', args=[self.ticket.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse('update_ticket', args=[self.ticket.pk]),
                {'status': 'Closed', 'assigned_to': ''},
            ).status_code,
            403,
        )

    def test_employee_can_create_ticket(self):
        self.login(self.employee)
        response = self.client.post(
            reverse('create_ticket'),
            {'subject': 'Email issue', 'description': 'Cannot send mail', 'category': 'Email', 'priority': 'High'},
        )
        self.assertRedirects(response, reverse('home'))
        self.assertTrue(Ticket.objects.filter(subject='Email issue', created_by=self.employee).exists())

    def test_details_page_shows_all_required_ticket_fields(self):
        self.ticket.assigned_to = self.support
        self.ticket.save()
        self.login(self.employee)
        response = self.client.get(reverse('ticket_detail', args=[self.ticket.pk]))
        self.assertContains(response, self.ticket.subject)
        self.assertContains(response, self.ticket.description)
        self.assertContains(response, self.ticket.category)
        self.assertContains(response, self.ticket.priority)
        self.assertContains(response, self.ticket.status)
        self.assertContains(response, self.employee.username)
        self.assertContains(response, self.support.username)

    def test_employee_can_comment_on_own_ticket_and_history_is_shown(self):
        self.login(self.employee)
        response = self.client.post(
            reverse('ticket_detail', args=[self.ticket.pk]),
            {'action': 'add_comment', 'text': 'Please call me before connecting.'},
        )
        self.assertRedirects(response, reverse('ticket_detail', args=[self.ticket.pk]))
        comment = Comment.objects.get(ticket=self.ticket)
        self.assertEqual(comment.author, self.employee)
        self.assertTrue(TicketActivity.objects.filter(
            ticket=self.ticket,
            event_type=TicketActivity.EventType.COMMENT,
        ).exists())
        response = self.client.get(reverse('ticket_detail', args=[self.ticket.pk]))
        self.assertContains(response, comment.text)
        self.assertContains(response, self.employee.username)

    def test_employee_cannot_comment_on_another_users_ticket(self):
        self.login(self.other_employee)
        response = self.client.post(
            reverse('ticket_detail', args=[self.ticket.pk]),
            {'action': 'add_comment', 'text': 'Unauthorized comment'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Comment.objects.filter(text='Unauthorized comment').exists())

    def test_authorized_attachment_upload_and_download(self):
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, True)
        self.login(self.employee)
        with override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse('upload_attachment', args=[self.ticket.pk]),
                {'file': SimpleUploadedFile('error.log', b'printer error details')},
            )
            self.assertRedirects(response, reverse('ticket_detail', args=[self.ticket.pk]))
            attachment = TicketAttachment.objects.get(ticket=self.ticket)
            response = self.client.get(reverse('download_attachment', args=[attachment.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment;', response['Content-Disposition'])
            response.close()
            self.assertTrue(TicketActivity.objects.filter(
                ticket=self.ticket,
                event_type=TicketActivity.EventType.ATTACHMENT,
            ).exists())

    def test_other_employee_cannot_download_ticket_attachment(self):
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, True)
        with override_settings(MEDIA_ROOT=media_root):
            self.login(self.employee)
            self.client.post(
                reverse('upload_attachment', args=[self.ticket.pk]),
                {'file': SimpleUploadedFile('details.txt', b'private details')},
            )
            attachment = TicketAttachment.objects.get(ticket=self.ticket)
            self.login(self.other_employee)
            response = self.client.get(reverse('download_attachment', args=[attachment.pk]))
            self.assertEqual(response.status_code, 403)

    def test_support_sees_all_and_can_assign_and_change_status_only(self):
        self.login(self.support)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Printer issue')
        response = self.client.post(
            reverse('update_ticket', args=[self.ticket.pk]),
            {'status': 'In Progress', 'assigned_to': self.support.pk, 'priority': 'Critical'},
        )
        self.assertRedirects(response, reverse('ticket_detail', args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'In Progress')
        self.assertEqual(self.ticket.assigned_to, self.support)
        self.assertEqual(self.ticket.priority, 'Medium')
        self.assertTrue(TicketActivity.objects.filter(
            ticket=self.ticket,
            event_type=TicketActivity.EventType.STATUS,
        ).exists())

    def test_support_cannot_create_ticket(self):
        self.login(self.support)
        self.assertEqual(self.client.get(reverse('create_ticket')).status_code, 403)

    def test_admin_has_full_ticket_access(self):
        self.login(self.admin_user)
        response = self.client.post(
            reverse('update_ticket', args=[self.ticket.pk]),
            {'status': 'Resolved', 'assigned_to': self.support.pk, 'priority': 'Critical'},
        )
        self.assertRedirects(response, reverse('ticket_detail', args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'Resolved')
        self.assertEqual(self.ticket.priority, 'Critical')
        self.assertEqual(self.client.get(reverse('create_ticket')).status_code, 200)

    def test_ticket_number_generation_and_uniqueness(self):
        # Create a first ticket
        ticket1 = Ticket.objects.create(
            subject='First ticket',
            description='Details 1',
            priority='Low',
            created_by=self.employee,
        )
        self.assertIsNotNone(ticket1.ticket_number)
        self.assertTrue(ticket1.ticket_number.startswith('IT-2026-'))
        
        # Create a second ticket
        ticket2 = Ticket.objects.create(
            subject='Second ticket',
            description='Details 2',
            priority='Medium',
            created_by=self.employee,
        )
        self.assertIsNotNone(ticket2.ticket_number)
        
        # Verify sequential number increments
        self.assertNotEqual(ticket1.ticket_number, ticket2.ticket_number)
        
        # Delete first ticket
        ticket1.delete()
        
        # Create a third ticket and check that there's no conflict or duplicates
        ticket3 = Ticket.objects.create(
            subject='Third ticket',
            description='Details 3',
            priority='High',
            created_by=self.employee,
        )
        self.assertIsNotNone(ticket3.ticket_number)
        self.assertNotEqual(ticket2.ticket_number, ticket3.ticket_number)

    def test_sla_logic(self):
        # Low SLA duration is 48 hours
        ticket_low = Ticket.objects.create(
            subject='Low ticket', priority='Low', created_by=self.employee
        )
        self.assertEqual(ticket_low.sla_duration.total_seconds(), 48 * 3600)

        # Critical SLA duration is 4 hours
        ticket_crit = Ticket.objects.create(
            subject='Crit ticket', priority='Critical', created_by=self.employee
        )
        self.assertEqual(ticket_crit.sla_duration.total_seconds(), 4 * 3600)
        
        # Check SLA remains unbreached on creation
        self.assertFalse(ticket_crit.is_sla_breached)

    def test_reports_dashboard_permissions(self):
        # Employee cannot access reports
        self.login(self.employee)
        response = self.client.get(reverse('reports_dashboard'))
        self.assertEqual(response.status_code, 403)
        
        # IT Support can access reports
        self.login(self.support)
        response = self.client.get(reverse('reports_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('monthly_labels', response.context)
        self.assertIn('category_labels', response.context)
        self.assertIn('engineer_labels', response.context)

    def test_audit_log_permissions_and_contents(self):
        # Employee cannot access audit log
        self.login(self.employee)
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.status_code, 403)
        
        # Admin can access audit log
        self.login(self.admin_user)
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('ticket_activities', response.context)
        self.assertIn('user_activities', response.context)
