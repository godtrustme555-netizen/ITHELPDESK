from django.contrib import admin
from .models import Asset, AssetAssignment, AssetActivity


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('asset_id', 'asset_type', 'brand', 'model', 'serial_number', 'status', 'location', 'purchase_date')
    search_fields = ('asset_id', 'brand', 'model', 'serial_number', 'location')
    list_filter = ('asset_type', 'status', 'location')
    ordering = ('-created_at',)


@admin.register(AssetAssignment)
class AssetAssignmentAdmin(admin.ModelAdmin):
    list_display = ('asset', 'employee', 'assigned_by', 'assigned_date', 'return_date')
    search_fields = ('asset__asset_id', 'asset__serial_number', 'employee__username', 'assigned_by__username')
    list_filter = ('assigned_date', 'return_date')
    ordering = ('-assigned_date',)


@admin.register(AssetActivity)
class AssetActivityAdmin(admin.ModelAdmin):
    list_display = ('asset', 'actor', 'action', 'timestamp')
    search_fields = ('asset__asset_id', 'action', 'notes', 'actor__username')
    list_filter = ('timestamp', 'action')
    ordering = ('-timestamp',)
