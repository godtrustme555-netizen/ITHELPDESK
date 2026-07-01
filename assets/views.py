import csv
import io
from datetime import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from accounts.models import get_user_role, user_can_manage_tickets
from .models import Asset, AssetAssignment, AssetActivity
from .forms import AssetForm, AssetAssignForm, AssetReturnForm, AssetStatusTransitionForm, CSVImportForm


def verify_asset_manager(user):
    """Ensure the user is Admin or IT Support."""
    if not user_can_manage_tickets(user):
        raise PermissionDenied("You do not have permission to access the Asset Management Module.")


@login_required
def assets_dashboard(request):
    verify_asset_manager(request.user)

    assets_query = Asset.objects.all().order_by('-created_at')

    # Statistics cards calculations
    total_assets = assets_query.count()
    assigned_assets = assets_query.filter(status='Assigned').count()
    available_assets = assets_query.filter(status='Available').count()
    repair_assets = assets_query.filter(status='Repair').count()

    # Search and filters parsing
    search_query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('type', '').strip()
    filter_status = request.GET.get('status', '').strip()

    if search_query:
        assets_query = assets_query.filter(
            Q(asset_id__icontains=search_query) |
            Q(brand__icontains=search_query) |
            Q(model__icontains=search_query) |
            Q(serial_number__icontains=search_query) |
            Q(location__icontains=search_query)
        )

    if filter_type:
        assets_query = assets_query.filter(asset_type=filter_type)

    if filter_status:
        assets_query = assets_query.filter(status=filter_status)

    # Chart data calculations
    all_assets = Asset.objects.all()
    type_counts = {choice[0]: all_assets.filter(asset_type=choice[0]).count() for choice in Asset.ASSET_TYPE_CHOICES}
    status_counts = {choice[0]: all_assets.filter(status=choice[0]).count() for choice in Asset.STATUS_CHOICES}

    context = {
        'assets': assets_query,
        'total_assets': total_assets,
        'assigned_assets': assigned_assets,
        'available_assets': available_assets,
        'repair_assets': repair_assets,
        'search_query': search_query,
        'filter_type': filter_type,
        'filter_status': filter_status,
        'asset_types': [choice[0] for choice in Asset.ASSET_TYPE_CHOICES],
        'status_choices': [choice[0] for choice in Asset.STATUS_CHOICES],
        'user_role': get_user_role(request.user),
        'chart_type_labels': list(type_counts.keys()),
        'chart_type_data': list(type_counts.values()),
        'chart_status_labels': list(status_counts.keys()),
        'chart_status_data': list(status_counts.values()),
    }

    return render(request, 'assets/assets_dashboard.html', context)


@login_required
def add_asset(request):
    verify_asset_manager(request.user)

    if request.method == 'POST':
        form = AssetForm(request.POST)
        if form.is_valid():
            asset = form.save()
            # Log AssetActivity
            AssetActivity.objects.create(
                asset=asset,
                actor=request.user,
                action="Asset Created",
                notes=f"Initial Status: {asset.status}. Location: {asset.location or 'N/A'}."
            )
            messages.success(request, f"Asset '{asset.brand} {asset.model}' successfully added with ID: {asset.asset_id}!")
            return redirect('assets_dashboard')
    else:
        form = AssetForm()

    context = {
        'form': form,
        'title': "Add New Asset",
        'user_role': get_user_role(request.user),
    }
    return render(request, 'assets/asset_form.html', context)


@login_required
def edit_asset(request, pk):
    verify_asset_manager(request.user)
    asset = get_object_or_404(Asset, pk=pk)

    if request.method == 'POST':
        form = AssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            # Log AssetActivity
            AssetActivity.objects.create(
                asset=asset,
                actor=request.user,
                action="Asset Modified",
                notes=f"Updated details. Location: {asset.location or 'N/A'}. Status: {asset.status}."
            )
            messages.success(request, f"Asset {asset.asset_id} successfully updated!")
            return redirect('asset_detail', pk=pk)
    else:
        form = AssetForm(instance=asset)

    context = {
        'form': form,
        'title': f"Edit Asset: {asset.asset_id}",
        'user_role': get_user_role(request.user),
    }
    return render(request, 'assets/asset_form.html', context)


@login_required
@require_POST
def delete_asset(request, pk):
    verify_asset_manager(request.user)
    asset = get_object_or_404(Asset, pk=pk)
    brand_model = f"{asset.brand} {asset.model}"
    asset_id = asset.asset_id
    asset.delete()
    messages.success(request, f"Asset '{brand_model}' ({asset_id}) deleted successfully.")
    return redirect('assets_dashboard')


@login_required
def asset_detail(request, pk):
    verify_asset_manager(request.user)
    asset = get_object_or_404(Asset, pk=pk)
    assignments = asset.assignments.select_related('employee', 'assigned_by').all().order_by('-assigned_date')
    activities = asset.activities.select_related('actor').all().order_by('-timestamp')

    # Get active assignment if present
    active_assignment = assignments.filter(return_date__isnull=True).first()

    context = {
        'asset': asset,
        'assignments': assignments,
        'active_assignment': active_assignment,
        'activities': activities,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'assets/asset_detail.html', context)


@login_required
def assign_asset(request, pk):
    verify_asset_manager(request.user)
    asset = get_object_or_404(Asset, pk=pk)

    if asset.status != 'Available':
        messages.error(request, f"Cannot assign asset {asset.asset_id} as its current status is '{asset.status}'.")
        return redirect('asset_detail', pk=pk)

    if request.method == 'POST':
        form = AssetAssignForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.asset = asset
            assignment.assigned_by = request.user
            assignment.save()

            # Set status to Assigned
            asset.status = 'Assigned'
            asset.save()

            # Log AssetActivity
            AssetActivity.objects.create(
                asset=asset,
                actor=request.user,
                action=f"Assigned to {assignment.employee.username}",
                notes=assignment.remarks or "No additional remarks."
            )

            messages.success(request, f"Asset {asset.asset_id} successfully assigned to {assignment.employee.username}!")
            return redirect('asset_detail', pk=pk)
    else:
        form = AssetAssignForm()

    context = {
        'form': form,
        'asset': asset,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'assets/assign_form.html', context)


@login_required
def return_asset(request, pk):
    verify_asset_manager(request.user)
    asset = get_object_or_404(Asset, pk=pk)

    if asset.status != 'Assigned':
        messages.error(request, f"Cannot return asset {asset.asset_id} as its current status is '{asset.status}'.")
        return redirect('asset_detail', pk=pk)

    active_assignment = asset.assignments.filter(return_date__isnull=True).first()
    if not active_assignment:
        messages.error(request, f"No active assignment record found for asset {asset.asset_id}.")
        return redirect('asset_detail', pk=pk)

    if request.method == 'POST':
        form = AssetReturnForm(request.POST)
        if form.is_valid():
            remarks = form.cleaned_data.get('remarks', '')
            active_assignment.return_date = timezone.now()
            if remarks:
                # Append return remarks if any remarks exist already
                original_remarks = active_assignment.remarks or ""
                active_assignment.remarks = f"{original_remarks}\n[Returned Remarks]: {remarks}".strip()
            active_assignment.save()

            # Set status to Available
            asset.status = 'Available'
            asset.save()

            # Log AssetActivity
            AssetActivity.objects.create(
                asset=asset,
                actor=request.user,
                action="Returned",
                notes=remarks or "Asset returned to available stock."
            )

            messages.success(request, f"Asset {asset.asset_id} successfully marked as returned!")
            return redirect('asset_detail', pk=pk)
    else:
        form = AssetReturnForm()

    context = {
        'form': form,
        'asset': asset,
        'assignment': active_assignment,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'assets/return_form.html', context)


@login_required
def change_asset_status(request, pk, status):
    verify_asset_manager(request.user)
    asset = get_object_or_404(Asset, pk=pk)

    allowed_transitions = ['Available', 'Repair', 'Scrap', 'Lost']
    if status not in allowed_transitions:
        messages.error(request, f"Invalid status transition to '{status}'.")
        return redirect('asset_detail', pk=pk)

    if request.method == 'POST':
        form = AssetStatusTransitionForm(request.POST)
        if form.is_valid():
            notes = form.cleaned_data.get('notes', '')
            old_status = asset.status

            # Close active assignment if transitioning from Assigned
            if old_status == 'Assigned':
                active_assignment = asset.assignments.filter(return_date__isnull=True).first()
                if active_assignment:
                    active_assignment.return_date = timezone.now()
                    orig_remarks = active_assignment.remarks or ""
                    active_assignment.remarks = f"{orig_remarks}\n[System Auto-Returned due to status change to {status}]: {notes}".strip()
                    active_assignment.save()

                    AssetActivity.objects.create(
                        asset=asset,
                        actor=request.user,
                        action="Assignment Auto-Returned",
                        notes=f"Asset transitioned to {status}. Auto-returned from {active_assignment.employee.username}."
                    )

            asset.status = status
            asset.save()

            # Log AssetActivity
            AssetActivity.objects.create(
                asset=asset,
                actor=request.user,
                action=f"Status changed to {status}",
                notes=notes or f"Status changed from {old_status} to {status}."
            )

            messages.success(request, f"Asset {asset.asset_id} status updated to {status} successfully.")
            return redirect('asset_detail', pk=pk)
    else:
        form = AssetStatusTransitionForm()

    context = {
        'form': form,
        'asset': asset,
        'status': status,
        'title': f"Mark Asset as {status}",
        'user_role': get_user_role(request.user),
    }
    return render(request, 'assets/status_form.html', context)


@login_required
def my_assets(request):
    assets_query = Asset.objects.filter(
        status='Assigned',
        assignments__employee=request.user,
        assignments__return_date__isnull=True
    ).distinct().order_by('-created_at')

    my_assets_list = []
    for asset in assets_query:
        active_assign = asset.assignments.filter(employee=request.user, return_date__isnull=True).first()
        my_assets_list.append({
            'asset': asset,
            'assignment': active_assign
        })

    context = {
        'my_assets': my_assets_list,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'assets/my_assets.html', context)


@login_required
def asset_history(request, pk):
    verify_asset_manager(request.user)
    asset = get_object_or_404(Asset, pk=pk)
    
    # Complete assignment history
    assignments = asset.assignments.select_related('employee', 'assigned_by').all().order_by('-assigned_date')
    
    # Return history specifically
    returns = assignments.filter(return_date__isnull=False)
    
    # Repair and other lifecycle history from activities
    repair_and_lifecycle = asset.activities.select_related('actor').filter(
        Q(action__icontains="Repair") | 
        Q(action__icontains="Scrap") | 
        Q(action__icontains="Lost") | 
        Q(action__icontains="Status changed")
    ).order_by('-timestamp')
    
    context = {
        'asset': asset,
        'assignments': assignments,
        'returns': returns,
        'repair_and_lifecycle': repair_and_lifecycle,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'assets/asset_history.html', context)


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Date '{date_str}' is not in a valid format. Please use YYYY-MM-DD or MM/DD/YYYY.")


@login_required
def import_assets_csv(request):
    verify_asset_manager(request.user)
    if request.method == 'POST':
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                decoded_file = csv_file.read().decode('utf-8-sig')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string)

                header = next(reader, None)
                if not header:
                    messages.error(request, "The uploaded CSV file is empty.")
                    return redirect('import_assets_csv')

                header_indices = {col.strip().lower(): idx for idx, col in enumerate(header)}

                type_keys = ['asset type', 'type', 'asset_type']
                brand_keys = ['brand']
                model_keys = ['model']
                serial_keys = ['serial number', 'serial', 'serial_number']
                purchase_date_keys = ['purchase date', 'purchase_date']
                warranty_expiry_keys = ['warranty expiry', 'warranty_expiry']
                status_keys = ['status']
                location_keys = ['location']
                remarks_keys = ['remarks', 'notes', 'remark']

                def find_index(keys):
                    for k in keys:
                        if k in header_indices:
                            return header_indices[k]
                    return None

                type_idx = find_index(type_keys)
                brand_idx = find_index(brand_keys)
                model_idx = find_index(model_keys)
                serial_idx = find_index(serial_keys)
                purchase_date_idx = find_index(purchase_date_keys)
                warranty_expiry_idx = find_index(warranty_expiry_keys)
                status_idx = find_index(status_keys)
                location_idx = find_index(location_keys)
                remarks_idx = find_index(remarks_keys)

                missing = []
                if type_idx is None: missing.append("Asset Type")
                if brand_idx is None: missing.append("Brand")
                if model_idx is None: missing.append("Model")
                if serial_idx is None: missing.append("Serial Number")
                if purchase_date_idx is None: missing.append("Purchase Date")
                if warranty_expiry_idx is None: missing.append("Warranty Expiry")

                if missing:
                    messages.error(request, f"Missing required headers in CSV: {', '.join(missing)}")
                    return redirect('import_assets_csv')

                imported_count = 0
                errors = []
                seen_serials = set()

                valid_types = [choice[0] for choice in Asset.ASSET_TYPE_CHOICES]
                valid_statuses = [choice[0] for choice in Asset.STATUS_CHOICES]

                with transaction.atomic():
                    for row_num, row in enumerate(reader, start=2):
                        if not row or all(not val.strip() for val in row):
                            continue

                        max_idx = max(type_idx, brand_idx, model_idx, serial_idx, purchase_date_idx, warranty_expiry_idx)
                        if remarks_idx is not None: max_idx = max(max_idx, remarks_idx)
                        if status_idx is not None: max_idx = max(max_idx, status_idx)
                        if location_idx is not None: max_idx = max(max_idx, location_idx)

                        if len(row) <= max_idx:
                            errors.append(f"Row {row_num}: Row has fewer columns than expected.")
                            continue

                        asset_type_val = row[type_idx].strip()
                        brand_val = row[brand_idx].strip()
                        model_val = row[model_idx].strip()
                        serial_val = row[serial_idx].strip()
                        purchase_date_val = row[purchase_date_idx].strip()
                        warranty_expiry_val = row[warranty_expiry_idx].strip()

                        status_val = 'Available'
                        if status_idx is not None and row[status_idx].strip():
                            inp_status = row[status_idx].strip().title()
                            if inp_status in valid_statuses:
                                status_val = inp_status
                            else:
                                errors.append(f"Row {row_num}: Invalid status '{row[status_idx].strip()}'. Valid: {', '.join(valid_statuses)}")
                                continue

                        location_val = ''
                        if location_idx is not None:
                            location_val = row[location_idx].strip()

                        remarks_val = ''
                        if remarks_idx is not None:
                            remarks_val = row[remarks_idx].strip()

                        matching_type = None
                        for vt in valid_types:
                            if vt.lower() == asset_type_val.lower():
                                matching_type = vt
                                break
                        if not matching_type:
                            errors.append(f"Row {row_num}: Invalid asset type '{asset_type_val}'. Valid: {', '.join(valid_types)}")
                            continue

                        if not brand_val:
                            errors.append(f"Row {row_num}: Brand is required.")
                            continue
                        if not model_val:
                            errors.append(f"Row {row_num}: Model is required.")
                            continue
                        if not serial_val:
                            errors.append(f"Row {row_num}: Serial number is required.")
                            continue

                        if serial_val in seen_serials:
                            errors.append(f"Row {row_num}: Duplicate serial number '{serial_val}' in CSV.")
                            continue
                        seen_serials.add(serial_val)

                        if Asset.objects.filter(serial_number=serial_val).exists():
                            errors.append(f"Row {row_num}: Asset with serial number '{serial_val}' already exists.")
                            continue

                        try:
                            p_date = parse_date(purchase_date_val)
                            if not p_date:
                                errors.append(f"Row {row_num}: Purchase date is required.")
                                continue
                        except ValueError as e:
                            errors.append(f"Row {row_num}: {str(e)}")
                            continue

                        try:
                            w_date = parse_date(warranty_expiry_val)
                            if not w_date:
                                errors.append(f"Row {row_num}: Warranty expiry date is required.")
                                continue
                        except ValueError as e:
                            errors.append(f"Row {row_num}: {str(e)}")
                            continue

                        asset = Asset(
                            asset_type=matching_type,
                            brand=brand_val,
                            model=model_val,
                            serial_number=serial_val,
                            purchase_date=p_date,
                            warranty_expiry=w_date,
                            status=status_val,
                            location=location_val,
                            remarks=remarks_val
                        )
                        asset.save()

                        AssetActivity.objects.create(
                            asset=asset,
                            actor=request.user,
                            action="Asset Created via Bulk CSV Import",
                            notes=f"Uploaded via CSV. Status: {status_val}. Location: {location_val or 'N/A'}."
                        )
                        imported_count += 1

                    if errors:
                        raise ValueError("CSV validation errors found.")

                messages.success(request, f"Successfully imported {imported_count} assets!")
                return redirect('assets_dashboard')

            except ValueError:
                context = {
                    'form': form,
                    'errors': errors,
                    'user_role': get_user_role(request.user),
                }
                return render(request, 'assets/import_form.html', context)
            except Exception as e:
                messages.error(request, f"Error processing CSV file: {str(e)}")
                return redirect('import_assets_csv')
    else:
        form = CSVImportForm()

    context = {
        'form': form,
        'user_role': get_user_role(request.user),
    }
    return render(request, 'assets/import_form.html', context)


@login_required
def export_assets_csv(request):
    verify_asset_manager(request.user)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="assets_inventory.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Asset ID', 'Asset Type', 'Brand', 'Model', 'Serial Number',
        'Purchase Date', 'Warranty Expiry', 'Status', 'Location', 'Remarks'
    ])

    assets = Asset.objects.all().order_by('-created_at')
    for asset in assets:
        writer.writerow([
            asset.asset_id,
            asset.asset_type,
            asset.brand,
            asset.model,
            asset.serial_number,
            asset.purchase_date.strftime('%Y-%m-%d') if asset.purchase_date else '',
            asset.warranty_expiry.strftime('%Y-%m-%d') if asset.warranty_expiry else '',
            asset.status,
            asset.location or '',
            asset.remarks or ''
        ])

    return response
