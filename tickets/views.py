from django.core.exceptions import PermissionDenied
from django.db.models.functions import TruncMonth
from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from accounts.models import get_user_role, user_can_manage_tickets, user_is_admin, UserActivityLog
from .models import Comment, Ticket, TicketActivity, TicketAttachment
from .forms import AttachmentForm, CommentForm, TicketForm, TicketUpdateForm


def get_authorized_ticket(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if not user_can_manage_tickets(request.user) and ticket.created_by != request.user:
        raise PermissionDenied("You can only access your own support tickets.")
    return ticket

@login_required
def home(request):
    can_manage = user_can_manage_tickets(request.user)
    if can_manage:
        tickets = Ticket.objects.all().order_by('-created_at')
    else:
        tickets = Ticket.objects.filter(created_by=request.user).order_by('-created_at')

    context = {
        'tickets': tickets,
        'total_tickets': tickets.count(),
        'open_tickets': tickets.filter(status='Open').count(),
        'in_progress_tickets': tickets.filter(status='In Progress').count(),
        'closed_tickets': tickets.filter(status__in=['Closed', 'Resolved']).count(),
        'user_role': get_user_role(request.user),
        'can_create_ticket': user_is_admin(request.user) or not can_manage,
    }

    return render(request, 'tickets/home.html', context)

@login_required
def create_ticket(request):
    if user_can_manage_tickets(request.user) and not user_is_admin(request.user):
        raise PermissionDenied("IT Support users cannot create employee tickets.")

    if request.method == 'POST':
        form = TicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.created_by = request.user
            ticket.save()
            TicketActivity.objects.create(
                ticket=ticket,
                actor=request.user,
                event_type=TicketActivity.EventType.CREATED,
                message='Ticket created',
            )
            messages.success(request, f"Ticket #{ticket.id} '{ticket.subject}' created successfully!")
            return redirect('home')
    else:
        form = TicketForm()

    return render(request, 'tickets/create_ticket.html', {'form': form})

@login_required
def ticket_detail(request, pk):
    ticket = get_authorized_ticket(request, pk)
    
    can_manage = user_can_manage_tickets(request.user)
    comments = ticket.comments.all().order_by('created_at')
    attachments = ticket.attachments.select_related('uploaded_by').order_by('-uploaded_at')
    activities = ticket.activities.select_related('actor').all()
    
    comment_form = CommentForm()
    attachment_form = AttachmentForm()
    is_admin = user_is_admin(request.user)
    update_form = TicketUpdateForm(instance=ticket, include_priority=is_admin) if can_manage else None

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_comment':
            comment_form = CommentForm(request.POST)
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.ticket = ticket
                comment.author = request.user
                comment.save()
                TicketActivity.objects.create(
                    ticket=ticket,
                    actor=request.user,
                    event_type=TicketActivity.EventType.COMMENT,
                    message='Added a comment',
                )
                messages.success(request, "Response added successfully.")
                return redirect('ticket_detail', pk=pk)
                
    context = {
        'ticket': ticket,
        'comments': comments,
        'comment_form': comment_form,
        'attachment_form': attachment_form,
        'attachments': attachments,
        'activities': activities,
        'update_form': update_form,
        'user_role': get_user_role(request.user),
        'can_change_priority': is_admin,
    }
    return render(request, 'tickets/ticket_detail.html', context)


@login_required
@require_POST
def update_ticket(request, pk):
    if not user_can_manage_tickets(request.user):
        raise PermissionDenied("Only IT Support and Admin users can update tickets.")

    ticket = get_object_or_404(Ticket, pk=pk)
    old_status = ticket.status
    old_assignee = ticket.assigned_to
    old_priority = ticket.priority
    is_admin = user_is_admin(request.user)
    form = TicketUpdateForm(request.POST, instance=ticket, include_priority=is_admin)
    if form.is_valid():
        form.save()
        if ticket.status != old_status:
            TicketActivity.objects.create(
                ticket=ticket,
                actor=request.user,
                event_type=TicketActivity.EventType.STATUS,
                message=f'Status changed from {old_status} to {ticket.status}',
            )
        if ticket.assigned_to != old_assignee:
            assignee = ticket.assigned_to.username if ticket.assigned_to else 'Unassigned'
            TicketActivity.objects.create(
                ticket=ticket,
                actor=request.user,
                event_type=TicketActivity.EventType.ASSIGNMENT,
                message=f'Assigned engineer changed to {assignee}',
            )
        if ticket.priority != old_priority:
            TicketActivity.objects.create(
                ticket=ticket,
                actor=request.user,
                event_type=TicketActivity.EventType.UPDATE,
                message=f'Priority changed from {old_priority} to {ticket.priority}',
            )
        messages.success(request, "Ticket details updated successfully.")
    else:
        messages.error(request, "Please correct the ticket update fields.")
    return redirect('ticket_detail', pk=pk)


@login_required
@require_POST
def upload_attachment(request, pk):
    ticket = get_authorized_ticket(request, pk)
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.ticket = ticket
        attachment.uploaded_by = request.user
        attachment.save()
        TicketActivity.objects.create(
            ticket=ticket,
            actor=request.user,
            event_type=TicketActivity.EventType.ATTACHMENT,
            message=f'Uploaded attachment: {attachment.filename}',
        )
        messages.success(request, "Attachment uploaded successfully.")
    else:
        for error in form.errors.get('file', []):
            messages.error(request, error)
    return redirect('ticket_detail', pk=pk)


@login_required
def download_attachment(request, pk):
    attachment = get_object_or_404(TicketAttachment.objects.select_related('ticket'), pk=pk)
    ticket = attachment.ticket
    if not user_can_manage_tickets(request.user) and ticket.created_by != request.user:
        raise PermissionDenied("You cannot download attachments from this ticket.")
    return FileResponse(
        attachment.file.open('rb'),
        as_attachment=True,
        filename=attachment.filename,
    )


@login_required
def reports_dashboard(request):
    if not user_can_manage_tickets(request.user):
        raise PermissionDenied("Only IT Support and Admin users can access the Reports Dashboard.")

    # 1. Monthly tickets aggregation
    monthly_stats = (
        Ticket.objects.annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    
    monthly_labels = []
    monthly_counts = []
    for entry in monthly_stats:
        if entry['month']:
            monthly_labels.append(entry['month'].strftime('%b %Y'))
            monthly_counts.append(entry['count'])

    # 2. Category wise tickets aggregation
    category_stats = (
        Ticket.objects.values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    category_labels = [entry['category'] for entry in category_stats]
    category_counts = [entry['count'] for entry in category_stats]

    # 3. Engineer wise tickets aggregation
    engineer_stats = (
        Ticket.objects.values('assigned_to__username')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    engineer_labels = []
    engineer_counts = []
    for entry in engineer_stats:
        username = entry['assigned_to__username']
        label = username if username else 'Unassigned'
        engineer_labels.append(label)
        engineer_counts.append(entry['count'])

    context = {
        'monthly_labels': monthly_labels,
        'monthly_counts': monthly_counts,
        'category_labels': category_labels,
        'category_counts': category_counts,
        'engineer_labels': engineer_labels,
        'engineer_counts': engineer_counts,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'tickets/reports.html', context)


@login_required
def audit_log(request):
    if not user_can_manage_tickets(request.user):
        raise PermissionDenied("Only IT Support and Admin users can access the Audit Log.")

    ticket_activities = TicketActivity.objects.select_related('ticket', 'actor').all().order_by('-created_at')[:200]
    user_activities = UserActivityLog.objects.select_related('user').all().order_by('-timestamp')[:200]

    context = {
        'ticket_activities': ticket_activities,
        'user_activities': user_activities,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'tickets/audit_log.html', context)

