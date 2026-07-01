from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from accounts.models import UserProfile
from .models import Asset, AssetAssignment, AssetActivity


class AssetModuleTests(TestCase):
    def setUp(self):
        # Create users with different roles
        self.employee = User.objects.create_user('employee', password='test-pass')
        self.employee.profile.role = UserProfile.Role.EMPLOYEE
        self.employee.profile.save()

        self.support = User.objects.create_user('support', password='test-pass')
        self.support.profile.role = UserProfile.Role.IT_SUPPORT
        self.support.profile.save()

        self.admin_user = User.objects.create_user('admin-user', password='test-pass')
        self.admin_user.profile.role = UserProfile.Role.ADMIN
        self.admin_user.profile.save()

        # Create a sample asset
        self.asset = Asset.objects.create(
            asset_type='Laptop',
            brand='Dell',
            model='Latitude 5430',
            serial_number='DEL-12345',
            purchase_date='2026-01-10',
            warranty_expiry='2029-01-10',
            status='Available',
            location='Main HQ',
            remarks='Sample note'
        )

    def login(self, user):
        self.client.force_login(user)

    def test_employee_access_denied(self):
        """Verify Employees receive 403 on all assets views."""
        self.login(self.employee)
        urls = [
            reverse('assets_dashboard'),
            reverse('add_asset'),
            reverse('asset_detail', args=[self.asset.pk]),
            reverse('assign_asset', args=[self.asset.pk]),
            reverse('return_asset', args=[self.asset.pk]),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_staff_access_granted(self):
        """Verify IT Support and Admin can access assets views."""
        self.login(self.support)
        response = self.client.get(reverse('assets_dashboard'))
        self.assertEqual(response.status_code, 200)

        self.login(self.admin_user)
        response = self.client.get(reverse('asset_detail', args=[self.asset.pk]))
        self.assertEqual(response.status_code, 200)

    def test_asset_id_sequencing(self):
        """Verify asset_id formats correctly (AST-0001, AST-0002) and sequentially handles deletions."""
        # Initial asset in setUp has AST-0001
        self.assertEqual(self.asset.asset_id, 'AST-0001')

        # Add second asset
        asset2 = Asset.objects.create(
            asset_type='Monitor',
            brand='LG',
            model='27UK850',
            serial_number='LG-MNT-55',
            purchase_date='2026-02-15',
            warranty_expiry='2028-02-15',
        )
        self.assertEqual(asset2.asset_id, 'AST-0002')

        # Delete first asset
        self.asset.delete()

        # Add third asset
        asset3 = Asset.objects.create(
            asset_type='Server',
            brand='HP',
            model='ProLiant DL360',
            serial_number='HP-SRV-99',
            purchase_date='2026-03-01',
            warranty_expiry='2031-03-01',
        )
        # Sequence continues: max of AST-0002 -> AST-0003
        self.assertEqual(asset3.asset_id, 'AST-0003')

    def test_asset_assignment_and_return_workflow(self):
        """Verify asset assignment changes status, logs record, and check-in resets state."""
        self.assertEqual(self.asset.status, 'Available')

        # Assign asset
        self.login(self.support)
        response = self.client.post(
            reverse('assign_asset', args=[self.asset.pk]),
            {'employee': self.employee.pk, 'remarks': 'Assigned for remote work.'}
        )
        self.assertRedirects(response, reverse('asset_detail', args=[self.asset.pk]))

        # Check status and assignment log
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, 'Assigned')
        self.assertEqual(self.asset.assignments.filter(return_date__isnull=True).count(), 1)

        # Return asset
        response = self.client.post(
            reverse('return_asset', args=[self.asset.pk]),
            {'remarks': 'Returned in perfect condition.'}
        )
        self.assertRedirects(response, reverse('asset_detail', args=[self.asset.pk]))

        # Check status reset and assignment closed
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, 'Available')
        self.assertEqual(self.asset.assignments.filter(return_date__isnull=True).count(), 0)
        self.assertEqual(self.asset.assignments.filter(return_date__isnull=False).count(), 1)

    def test_dashboard_aggregations(self):
        """Verify dashboard cards count correctly."""
        # Setup additional assets
        Asset.objects.create(
            asset_type='Desktop', brand='Lenovo', model='M70q', serial_number='LEN-1',
            purchase_date='2026-01-01', warranty_expiry='2029-01-01', status='Available'
        )
        Asset.objects.create(
            asset_type='Printer', brand='HP', model='LaserJet', serial_number='HP-2',
            purchase_date='2026-01-01', warranty_expiry='2029-01-01', status='Repair'
        )
        Asset.objects.create(
            asset_type='Laptop', brand='Apple', model='MacBook Air', serial_number='APL-3',
            purchase_date='2026-01-01', warranty_expiry='2029-01-01', status='Assigned'
        )

        self.login(self.support)
        response = self.client.get(reverse('assets_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # We have 1 Laptop ( Dell, Available) in setUp
        # Plus 1 Lenovo (Available), 1 HP Printer (Repair), 1 Apple Laptop (Assigned)
        # Total = 4
        # Available = 2
        # Assigned = 1
        # Repair = 1
        self.assertEqual(response.context['total_assets'], 4)
        self.assertEqual(response.context['available_assets'], 2)
        self.assertEqual(response.context['assigned_assets'], 1)
        self.assertEqual(response.context['repair_assets'], 1)

    def test_employee_my_assets(self):
        """Verify Employees can access their own assigned assets, and only theirs."""
        # Assign self.asset to employee
        AssetAssignment.objects.create(
            asset=self.asset,
            employee=self.employee,
            assigned_by=self.admin_user,
            remarks="Assigned for testing employee portal"
        )
        # Update asset status
        self.asset.status = 'Assigned'
        self.asset.save()

        # Create another asset assigned to support user
        asset2 = Asset.objects.create(
            asset_type='Laptop', brand='HP', model='ProBook', serial_number='HP-PRO',
            purchase_date='2026-01-01', warranty_expiry='2029-01-01', status='Assigned'
        )
        AssetAssignment.objects.create(
            asset=asset2, employee=self.support, assigned_by=self.admin_user
        )

        # Login as employee
        self.login(self.employee)
        response = self.client.get(reverse('my_assets'))
        self.assertEqual(response.status_code, 200)
        
        # Check context
        my_assets = response.context['my_assets']
        self.assertEqual(len(my_assets), 1)
        self.assertEqual(my_assets[0]['asset'], self.asset)

    def test_lifecycle_status_transitions(self):
        """Verify Repair, Scrap, and Lost status transitions log AssetActivity."""
        self.login(self.support)
        
        # Available -> Repair transition
        url = reverse('change_asset_status', args=[self.asset.pk, 'Repair'])
        response = self.client.post(url, {'notes': 'Screen flickering, sending to service center.'})
        self.assertRedirects(response, reverse('asset_detail', args=[self.asset.pk]))
        
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, 'Repair')
        
        # Check AssetActivity log
        activity = self.asset.activities.order_by('-timestamp').first()
        self.assertEqual(activity.action, 'Status changed to Repair')
        self.assertEqual(activity.notes, 'Screen flickering, sending to service center.')
        self.assertEqual(activity.actor, self.support)

        # Let's test transitioning from Assigned: should auto-return and close assignment
        self.asset.status = 'Assigned'
        self.asset.save()
        assign = AssetAssignment.objects.create(
            asset=self.asset, employee=self.employee, assigned_by=self.support
        )
        
        url_scrap = reverse('change_asset_status', args=[self.asset.pk, 'Scrap'])
        response = self.client.post(url_scrap, {'notes': 'Water damage. Beyond economic repair.'})
        self.assertRedirects(response, reverse('asset_detail', args=[self.asset.pk]))
        
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, 'Scrap')
        
        # Verify assignment is closed
        assign.refresh_from_db()
        self.assertIsNotNone(assign.return_date)
        self.assertIn('[System Auto-Returned due to status change to Scrap]', assign.remarks)
        
        # Verify both AssetActivity objects are logged: Auto-Returned and Scrap Status change
        activities = self.asset.activities.order_by('-timestamp')
        self.assertTrue(activities.filter(action='Assignment Auto-Returned').exists())
        self.assertTrue(activities.filter(action='Status changed to Scrap').exists())

    def test_export_assets_csv(self):
        """Verify CSV export is formatted properly with header and entries."""
        self.login(self.support)
        response = self.client.get(reverse('export_assets_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename="assets_inventory.csv"', response['Content-Disposition'])
        
        content = response.content.decode('utf-8')
        lines = content.strip().split('\r\n')
        self.assertGreaterEqual(len(lines), 2)
        
        # Check Header
        headers = lines[0].split(',')
        self.assertEqual(headers[0], 'Asset ID')
        self.assertEqual(headers[4], 'Serial Number')
        
        # Check Asset Row
        asset_row = lines[1].split(',')
        self.assertEqual(asset_row[4], self.asset.serial_number)

    def test_import_assets_csv(self):
        """Verify importing valid CSV works and invalid values/duplicates fail correctly."""
        self.login(self.support)
        
        # 1. Test Valid CSV Upload
        import io
        csv_data = (
            "Type,Brand,Model,Serial Number,Purchase Date,Warranty Expiry,Status,Location,Remarks\n"
            "Laptop,Apple,MacBook Air M2,APL-MB-999,2026-06-01,2029-06-01,Available,HQ Room 101,New hire laptop\n"
            "UPS,APC,Back-UPS Pro,APC-UPS-777,2026-06-05,2028-06-05,Available,Server Closet,Backup power"
        )
        csv_file = io.BytesIO(csv_data.encode('utf-8'))
        csv_file.name = 'test_assets.csv'
        
        response = self.client.post(
            reverse('import_assets_csv'),
            {'csv_file': csv_file}
        )
        self.assertRedirects(response, reverse('assets_dashboard'))
        
        # Assets should be created
        self.assertTrue(Asset.objects.filter(serial_number='APL-MB-999').exists())
        self.assertTrue(Asset.objects.filter(serial_number='APC-UPS-777').exists())
        
        apple_laptop = Asset.objects.get(serial_number='APL-MB-999')
        self.assertEqual(apple_laptop.brand, 'Apple')
        self.assertEqual(apple_laptop.model, 'MacBook Air M2')
        self.assertEqual(apple_laptop.location, 'HQ Room 101')
        
        # Check AssetActivity
        activity = apple_laptop.activities.first()
        self.assertEqual(activity.action, 'Asset Created via Bulk CSV Import')
        
        # 2. Test Invalid CSV Upload (Duplicate Serial)
        csv_dup_data = (
            "Type,Brand,Model,Serial Number,Purchase Date,Warranty Expiry,Status,Location,Remarks\n"
            "Monitor,LG,27 Inch,DEL-12345,2026-06-01,2029-06-01,Available,HQ Room 101,Duplicate serial"
        )
        csv_dup_file = io.BytesIO(csv_dup_data.encode('utf-8'))
        csv_dup_file.name = 'test_dup.csv'
        
        response_dup = self.client.post(
            reverse('import_assets_csv'),
            {'csv_file': csv_dup_file}
        )
        # Should stay on page and show errors
        self.assertEqual(response_dup.status_code, 200)
        self.assertIn('errors', response_dup.context)
        self.assertTrue(any("already exists" in err for err in response_dup.context['errors']))

    def test_asset_history_page(self):
        """Verify the Asset History page displays assignment, return, and lifecycle actions."""
        # 1. Create assignment record (which is open)
        assign = AssetAssignment.objects.create(
            asset=self.asset,
            employee=self.employee,
            assigned_by=self.support,
            remarks="Allocating device"
        )
        self.asset.status = 'Assigned'
        self.asset.save()

        # 2. Add custom repair activity
        activity = AssetActivity.objects.create(
            asset=self.asset,
            actor=self.support,
            action="Status changed to Repair",
            notes="Replacing logic board"
        )

        # Login as support
        self.login(self.support)
        response = self.client.get(reverse('asset_history', args=[self.asset.pk]))
        self.assertEqual(response.status_code, 200)

        # Assert context variables are populated correctly
        self.assertIn('assignments', response.context)
        self.assertIn('returns', response.context)
        self.assertIn('repair_and_lifecycle', response.context)

        # Active assignment list should have 1 item, return history should be empty
        self.assertEqual(len(response.context['assignments']), 1)
        self.assertEqual(len(response.context['returns']), 0)
        self.assertEqual(len(response.context['repair_and_lifecycle']), 1)
