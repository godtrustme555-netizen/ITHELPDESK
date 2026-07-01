from django import forms
from django.contrib.auth.models import User
from .models import Comment, Ticket, TicketAttachment
from accounts.models import UserProfile

class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ['subject', 'description', 'category', 'priority']
        widgets = {
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'What is the issue?'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe the issue in detail...'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
        }

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Add a response or update...',
                'required': True
            }),
        }

class TicketUpdateForm(forms.ModelForm):
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Unassigned",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Assign Agent"
    )

    class Meta:
        model = Ticket
        fields = ['status', 'priority', 'assigned_to']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, include_priority=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.filter(
            profile__role__in=[
                UserProfile.Role.ADMIN,
                UserProfile.Role.IT_SUPPORT,
            ]
        ).order_by('username')
        if not include_priority:
            self.fields.pop('priority')


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = TicketAttachment
        fields = ['file']
        widgets = {
            'file': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': '.png,.jpg,.jpeg,.gif,.pdf,.txt,.log,.doc,.docx,.xls,.xlsx,.zip',
            }),
        }

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        if uploaded_file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('Attachment must be 10 MB or smaller.')
        allowed_extensions = {
            'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'log',
            'doc', 'docx', 'xls', 'xlsx', 'zip',
        }
        extension = uploaded_file.name.rsplit('.', 1)[-1].lower() if '.' in uploaded_file.name else ''
        if extension not in allowed_extensions:
            raise forms.ValidationError('This file type is not supported.')
        return uploaded_file


