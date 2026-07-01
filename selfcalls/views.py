import csv
import io
from datetime import datetime
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.http import FileResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from accounts.models import get_user_role, user_can_manage_tickets, user_is_admin
from .models import SelfCall, SelfCallComment, SelfCallAttachment, SelfCallActivity
from .forms import SelfCallForm, SelfCallUpdateForm, SelfCallCommentForm, SelfCallAttachmentForm


def verify_self_call_manager(user):
    """Ensure the user is Admin or IT Support."""
    if not user_can_manage_tickets(user):
        raise PermissionDenied("You do not have permission to access the IT Department Self Call Module.")


@login_required
def self_call_dashboard(request):
    verify_self_call_manager(request.user)

    self_calls_query = SelfCall.objects.all().order_by('-created_date')

    # Overall statistics cards
    stats = {
        'total': self_calls_query.count(),
        'open': self_calls_query.filter(status='Open').count(),
        'assigned': self_calls_query.filter(status='Assigned').count(),
        'in_progress': self_calls_query.filter(status='In Progress').count(),
        'completed': self_calls_query.filter(status='Completed').count(),
        'closed': self_calls_query.filter(status='Closed').count(),
        'cancelled': self_calls_query.filter(status='Cancelled').count(),
    }

    # Filters parsing
    search_query = request.GET.get('q', '').strip()
    filter_status = request.GET.get('status', '').strip()
    filter_priority = request.GET.get('priority', '').strip()
    filter_category = request.GET.get('category', '').strip()
    filter_department = request.GET.get('department', '').strip()
    filter_engineer = request.GET.get('engineer', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()

    if search_query:
        self_calls_query = self_calls_query.filter(
            Q(self_call_id__icontains=search_query) |
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    if filter_status and filter_status != 'all':
        self_calls_query = self_calls_query.filter(status=filter_status)

    if filter_priority and filter_priority != 'all':
        self_calls_query = self_calls_query.filter(priority=filter_priority)

    if filter_category and filter_category != 'all':
        self_calls_query = self_calls_query.filter(category=filter_category)

    if filter_department and filter_department != 'all':
        self_calls_query = self_calls_query.filter(department=filter_department)

    if filter_engineer and filter_engineer != 'all':
        if filter_engineer == 'unassigned':
            self_calls_query = self_calls_query.filter(assigned_engineer__isnull=True)
        else:
            self_calls_query = self_calls_query.filter(assigned_engineer_id=filter_engineer)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            self_calls_query = self_calls_query.filter(created_date__gte=start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            # include the whole day
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            self_calls_query = self_calls_query.filter(created_date__lte=end_dt)
        except ValueError:
            pass

    engineers = User.objects.filter(
        profile__role__in=['ADMIN', 'IT_SUPPORT']
    ).order_by('username')

    context = {
        'self_calls': self_calls_query,
        'stats': stats,
        'engineers': engineers,
        'user_role': get_user_role(request.user),
        'categories': [c[0] for c in SelfCall.CATEGORY_CHOICES],
        'priorities': [p[0] for p in SelfCall.PRIORITY_CHOICES],
        'statuses': [s[0] for s in SelfCall.STATUS_CHOICES],
        'departments': [d[0] for d in SelfCall.DEPARTMENT_CHOICES],
        
        # filters preservation
        'selected_q': search_query,
        'selected_status': filter_status,
        'selected_priority': filter_priority,
        'selected_category': filter_category,
        'selected_department': filter_department,
        'selected_engineer': filter_engineer,
        'selected_start_date': start_date,
        'selected_end_date': end_date,
    }

    return render(request, 'selfcalls/dashboard.html', context)


@login_required
def create_self_call(request):
    verify_self_call_manager(request.user)

    if request.method == 'POST':
        form = SelfCallForm(request.POST)
        if form.is_valid():
            self_call = form.save(commit=False)
            self_call.created_by = request.user
            self_call.save()

            # Activity log creation
            SelfCallActivity.objects.create(
                self_call=self_call,
                actor=request.user,
                event_type=SelfCallActivity.EventType.CREATED,
                message='Self Call created'
            )

            # If engineer is assigned at creation
            if self_call.assigned_engineer:
                SelfCallActivity.objects.create(
                    self_call=self_call,
                    actor=request.user,
                    event_type=SelfCallActivity.EventType.ASSIGNED,
                    message=f'Assigned engineer to {self_call.assigned_engineer.username}'
                )

            messages.success(request, f"Self Call {self_call.self_call_id or ''} created successfully!")
            return redirect('self_call_dashboard')
    else:
        form = SelfCallForm()

    return render(request, 'selfcalls/create_self_call.html', {
        'form': form,
        'user_role': get_user_role(request.user)
    })


@login_required
def self_call_detail(request, pk):
    verify_self_call_manager(request.user)
    self_call = get_object_or_404(SelfCall, pk=pk)

    comments = self_call.comments.select_related('author').all().order_by('created_at')
    attachments = self_call.attachments.select_related('uploaded_by').all().order_by('-uploaded_at')
    activities = self_call.activities.select_related('actor').all()

    comment_form = SelfCallCommentForm()
    attachment_form = SelfCallAttachmentForm()
    update_form = SelfCallUpdateForm(instance=self_call)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_comment':
            comment_form = SelfCallCommentForm(request.POST)
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.self_call = self_call
                comment.author = request.user
                comment.save()

                # Activity logging
                SelfCallActivity.objects.create(
                    self_call=self_call,
                    actor=request.user,
                    event_type=SelfCallActivity.EventType.COMMENT,
                    message='Added a comment'
                )
                messages.success(request, "Comment added successfully.")
                return redirect('self_call_detail', pk=pk)

    context = {
        'self_call': self_call,
        'comments': comments,
        'attachments': attachments,
        'activities': activities,
        'comment_form': comment_form,
        'attachment_form': attachment_form,
        'update_form': update_form,
        'user_role': get_user_role(request.user),
    }

    return render(request, 'selfcalls/self_call_detail.html', context)


@login_required
@require_POST
def update_self_call(request, pk):
    verify_self_call_manager(request.user)
    self_call = get_object_or_404(SelfCall, pk=pk)

    old_status = self_call.status
    old_priority = self_call.priority
    old_engineer = self_call.assigned_engineer
    old_planned_date = self_call.planned_date
    old_est_hours = self_call.estimated_hours
    old_act_hours = self_call.actual_hours
    old_remarks = self_call.remarks

    form = SelfCallUpdateForm(request.POST, instance=self_call)
    if form.is_valid():
        form.save()

        # Generate individual activity logs for tracking modifications
        if self_call.status != old_status:
            SelfCallActivity.objects.create(
                self_call=self_call,
                actor=request.user,
                event_type=SelfCallActivity.EventType.STATUS,
                message=f'Status changed from {old_status} to {self_call.status}'
            )
            # Log as closed event type if marked closed
            if self_call.status in ['Completed', 'Closed']:
                SelfCallActivity.objects.create(
                    self_call=self_call,
                    actor=request.user,
                    event_type=SelfCallActivity.EventType.CLOSED,
                    message=f'Task finalized with status: {self_call.status}'
                )

        if self_call.assigned_engineer != old_engineer:
            eng_name = self_call.assigned_engineer.username if self_call.assigned_engineer else 'Unassigned'
            SelfCallActivity.objects.create(
                self_call=self_call,
                actor=request.user,
                event_type=SelfCallActivity.EventType.ASSIGNED,
                message=f'Assigned engineer changed to {eng_name}'
            )
            if self_call.status == 'Open' and self_call.assigned_engineer:
                self_call.status = 'Assigned'
                self_call.save()

        if self_call.priority != old_priority:
            SelfCallActivity.objects.create(
                self_call=self_call,
                actor=request.user,
                event_type=SelfCallActivity.EventType.UPDATE,
                message=f'Priority changed from {old_priority} to {self_call.priority}'
            )

        if self_call.planned_date != old_planned_date:
            SelfCallActivity.objects.create(
                self_call=self_call,
                actor=request.user,
                event_type=SelfCallActivity.EventType.UPDATE,
                message='Planned Date updated'
            )

        if self_call.estimated_hours != old_est_hours or self_call.actual_hours != old_act_hours:
            SelfCallActivity.objects.create(
                self_call=self_call,
                actor=request.user,
                event_type=SelfCallActivity.EventType.UPDATE,
                message='Work hours details updated'
            )

        if self_call.remarks != old_remarks:
            SelfCallActivity.objects.create(
                self_call=self_call,
                actor=request.user,
                event_type=SelfCallActivity.EventType.UPDATE,
                message='Remarks updated'
            )

        messages.success(request, "Self Call details updated successfully.")
    else:
        messages.error(request, "Please correct the errors in the update form.")

    return redirect('self_call_detail', pk=pk)


@login_required
@require_POST
def upload_attachment(request, pk):
    verify_self_call_manager(request.user)
    self_call = get_object_or_404(SelfCall, pk=pk)

    form = SelfCallAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.self_call = self_call
        attachment.uploaded_by = request.user
        attachment.save()

        # Log action
        SelfCallActivity.objects.create(
            self_call=self_call,
            actor=request.user,
            event_type=SelfCallActivity.EventType.ATTACHMENT,
            message=f'Uploaded attachment: {attachment.filename}'
        )
        messages.success(request, "File uploaded successfully.")
    else:
        for error in form.errors.get('file', []):
            messages.error(request, error)

    return redirect('self_call_detail', pk=pk)


@login_required
def download_attachment(request, pk):
    verify_self_call_manager(request.user)
    attachment = get_object_or_404(SelfCallAttachment, pk=pk)
    return FileResponse(
        attachment.file.open('rb'),
        as_attachment=True,
        filename=attachment.filename
    )


@login_required
def reports(request):
    verify_self_call_manager(request.user)

    # 1. Category Wise
    category_data = SelfCall.objects.values('category').annotate(count=Count('id')).order_by('-count')
    category_labels = [c['category'] for c in category_data]
    category_counts = [c['count'] for c in category_data]

    # 2. Status Wise
    status_data = SelfCall.objects.values('status').annotate(count=Count('id')).order_by('-count')
    status_labels = [s['status'] for s in status_data]
    status_counts = [s['count'] for s in status_data]

    # 3. Engineer Wise (Workload)
    engineer_data = SelfCall.objects.values('assigned_engineer__username').annotate(count=Count('id')).order_by('-count')
    engineer_labels = []
    engineer_counts = []
    for eng in engineer_data:
        label = eng['assigned_engineer__username'] or 'Unassigned'
        engineer_labels.append(label)
        engineer_counts.append(eng['count'])

    # 4. Monthly Self Calls
    monthly_data = (
        SelfCall.objects.annotate(month=TruncMonth('created_date'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    monthly_labels = []
    monthly_counts = []
    for m in monthly_data:
        if m['month']:
            monthly_labels.append(m['month'].strftime('%b %Y'))
            monthly_counts.append(m['count'])

    # 5. Department Wise
    department_data = SelfCall.objects.values('department').annotate(count=Count('id')).order_by('-count')
    department_labels = [d['department'] for d in department_data]
    department_counts = [d['count'] for d in department_data]

    context = {
        'category_labels': category_labels,
        'category_counts': category_counts,
        'status_labels': status_labels,
        'status_counts': status_counts,
        'engineer_labels': engineer_labels,
        'engineer_counts': engineer_counts,
        'monthly_labels': monthly_labels,
        'monthly_counts': monthly_counts,
        'department_labels': department_labels,
        'department_counts': department_counts,
        'department_data': zip(department_labels, department_counts),
        'user_role': get_user_role(request.user),
    }

    return render(request, 'selfcalls/reports.html', context)


@login_required
def export_self_calls(request):
    verify_self_call_manager(request.user)

    export_format = request.GET.get('format', 'csv').lower()
    self_calls = SelfCall.objects.all().order_by('-created_date')

    # Re-apply same filters as dashboard
    search_query = request.GET.get('q', '').strip()
    filter_status = request.GET.get('status', '').strip()
    filter_priority = request.GET.get('priority', '').strip()
    filter_category = request.GET.get('category', '').strip()
    filter_department = request.GET.get('department', '').strip()
    filter_engineer = request.GET.get('engineer', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()

    if search_query:
        self_calls = self_calls.filter(
            Q(self_call_id__icontains=search_query) |
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    if filter_status and filter_status != 'all':
        self_calls = self_calls.filter(status=filter_status)
    if filter_priority and filter_priority != 'all':
        self_calls = self_calls.filter(priority=filter_priority)
    if filter_category and filter_category != 'all':
        self_calls = self_calls.filter(category=filter_category)
    if filter_department and filter_department != 'all':
        self_calls = self_calls.filter(department=filter_department)
    if filter_engineer and filter_engineer != 'all':
        if filter_engineer == 'unassigned':
            self_calls = self_calls.filter(assigned_engineer__isnull=True)
        else:
            self_calls = self_calls.filter(assigned_engineer_id=filter_engineer)
    if start_date:
        self_calls = self_calls.filter(created_date__date__gte=start_date)
    if end_date:
        self_calls = self_calls.filter(created_date__date__lte=end_date)

    if export_format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="self_calls_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Self Call ID', 'Title', 'Description', 'Category', 'Priority',
            'Status', 'Department', 'Assigned Engineer', 'Created By',
            'Created Date', 'Planned Date', 'Completed Date', 'Est Hours', 'Act Hours', 'Remarks'
        ])
        for sc in self_calls:
            writer.writerow([
                sc.self_call_id, sc.title, sc.description, sc.category, sc.priority,
                sc.status, sc.department,
                sc.assigned_engineer.username if sc.assigned_engineer else 'Unassigned',
                sc.created_by.username,
                sc.created_date.strftime('%Y-%m-%d %H:%M') if sc.created_date else '',
                sc.planned_date.strftime('%Y-%m-%d %H:%M') if sc.planned_date else '',
                sc.completed_date.strftime('%Y-%m-%d %H:%M') if sc.completed_date else '',
                sc.estimated_hours or '',
                sc.actual_hours or '',
                sc.remarks or ''
            ])
        return response

    elif export_format == 'excel':
        # Excel XML/HTML representation (highly compatible with excel)
        response = HttpResponse(content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="self_calls_export.xls"'
        
        # Build standard HTML output
        html_str = """
        <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
        <head><meta charset="utf-8"><!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet><x:Name>Self Calls</x:Name><x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]--></head>
        <body>
        <table border="1">
            <tr style="background-color: #1e3a8a; color: white; font-weight: bold;">
                <th>Self Call ID</th>
                <th>Title</th>
                <th>Description</th>
                <th>Category</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Department</th>
                <th>Assigned Engineer</th>
                <th>Created By</th>
                <th>Created Date</th>
                <th>Planned Date</th>
                <th>Completed Date</th>
                <th>Est Hours</th>
                <th>Act Hours</th>
                <th>Remarks</th>
            </tr>
        """
        for sc in self_calls:
            html_str += f"""
            <tr>
                <td>{sc.self_call_id or ''}</td>
                <td>{sc.title}</td>
                <td>{sc.description}</td>
                <td>{sc.category}</td>
                <td>{sc.priority}</td>
                <td>{sc.status}</td>
                <td>{sc.department}</td>
                <td>{sc.assigned_engineer.username if sc.assigned_engineer else 'Unassigned'}</td>
                <td>{sc.created_by.username}</td>
                <td>{sc.created_date.strftime('%Y-%m-%d %H:%M') if sc.created_date else ''}</td>
                <td>{sc.planned_date.strftime('%Y-%m-%d %H:%M') if sc.planned_date else ''}</td>
                <td>{sc.completed_date.strftime('%Y-%m-%d %H:%M') if sc.completed_date else ''}</td>
                <td>{sc.estimated_hours or ''}</td>
                <td>{sc.actual_hours or ''}</td>
                <td>{sc.remarks or ''}</td>
            </tr>
            """
        html_str += "</table></body></html>"
        response.write(html_str)
        return response

    elif export_format == 'pdf':
        # PDF print preview page triggering window.print() (highly professional browser support fallback)
        return render(request, 'selfcalls/export_pdf.html', {
            'self_calls': self_calls,
            'exported_at': timezone.now()
        })

    return redirect('self_call_dashboard')
