from django import forms
from django.contrib.auth.models import User
from .models import SelfCall, SelfCallComment, SelfCallAttachment
from accounts.models import UserProfile


class SelfCallForm(forms.ModelForm):
    assigned_engineer = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Unassigned",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Assigned Engineer"
    )

    class Meta:
        model = SelfCall
        fields = [
            'title', 'description', 'category', 'priority', 'department',
            'assigned_engineer', 'planned_date', 'estimated_hours', 'remarks', 'sla_enabled'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Task title (e.g. daily backup check)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe the work details...'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'planned_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'estimated_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': 'e.g. 2.5'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Any initial notes...'}),
            'sla_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_engineer'].queryset = User.objects.filter(
            profile__role__in=[UserProfile.Role.ADMIN, UserProfile.Role.IT_SUPPORT]
        ).order_by('username')


class SelfCallUpdateForm(forms.ModelForm):
    assigned_engineer = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Unassigned",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Assigned Engineer"
    )

    class Meta:
        model = SelfCall
        fields = ['status', 'priority', 'assigned_engineer', 'planned_date', 'estimated_hours', 'actual_hours', 'remarks']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'planned_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'estimated_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
            'actual_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': 'e.g. 3.0'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Update remarks...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_engineer'].queryset = User.objects.filter(
            profile__role__in=[UserProfile.Role.ADMIN, UserProfile.Role.IT_SUPPORT]
        ).order_by('username')


class SelfCallCommentForm(forms.ModelForm):
    class Meta:
        model = SelfCallComment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Add internal engineer comment...',
                'required': True
            }),
        }


class SelfCallAttachmentForm(forms.ModelForm):
    class Meta:
        model = SelfCallAttachment
        fields = ['file']
        widgets = {
            'file': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.docx,.xlsx,.png,.jpg,.jpeg,.zip',
            }),
        }

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        # Enforce max 20 MB size limit
        if uploaded_file.size > 20 * 1024 * 1024:
            raise forms.ValidationError('Attachment must be 20 MB or smaller.')
        allowed_extensions = {'pdf', 'docx', 'xlsx', 'png', 'jpg', 'jpeg', 'zip'}
        extension = uploaded_file.name.rsplit('.', 1)[-1].lower() if '.' in uploaded_file.name else ''
        if extension not in allowed_extensions:
            raise forms.ValidationError('This file type is not supported. Supported: PDF, DOCX, XLSX, PNG, JPG, ZIP')
        return uploaded_file
