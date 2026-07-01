from django import forms
from django.contrib.auth.models import User
from .models import Asset, AssetAssignment


class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ['asset_type', 'brand', 'model', 'serial_number', 'purchase_date', 'warranty_expiry', 'status', 'location', 'remarks']
        widgets = {
            'asset_type': forms.Select(attrs={'class': 'form-select'}),
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Dell, HP, Apple'}),
            'model': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Latitude 5420, MacBook Pro'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Unique Serial/Service tag'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'warranty_expiry': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. HQ - Room 402, Remote'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Any other technical details...'}),
        }


class AssetAssignForm(forms.ModelForm):
    employee = forms.ModelChoiceField(
        queryset=User.objects.all().order_by('username'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Employee"
    )

    class Meta:
        model = AssetAssignment
        fields = ['employee', 'remarks']
        widgets = {
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter assignment details or remarks...'}),
        }


class AssetReturnForm(forms.Form):
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Condition of the asset upon return...'}),
        required=False,
        label="Remarks"
    )


class AssetStatusTransitionForm(forms.Form):
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Reason/remarks for this status change...'}),
        required=False,
        label="Status Change Remarks"
    )


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'}),
        label="CSV File"
    )

