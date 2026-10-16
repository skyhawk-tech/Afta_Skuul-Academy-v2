import re
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from .models import Batch

User = get_user_model()


# ============================================================================
# CUSTOM VALIDATORS
# ============================================================================

def validate_phone(value):
    """Validate that the phone number contains only digits, spaces, '+', '-' and parentheses."""
    if value and not re.match(r'^[\+\d\s\-\(\)]{7,15}$', value):
        raise ValidationError(
            _('Enter a valid phone number (e.g., +254 712 345 678).')
        )
    return value


# ============================================================================
# BATCH FORM
# ============================================================================

class BatchForm(forms.ModelForm):
    """
    Form for creating and editing tuition batches.
    Includes validation for name uniqueness, capacity, and fees.
    """

    class Meta:
        model = Batch
        fields = ['name', 'subject', 'grade_level', 'max_capacity', 'fee_per_session', 'schedule']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('e.g., Math G4 - Mon/Wed'),
                'autofocus': True,
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('e.g., Mathematics, English, Science'),
            }),
            'grade_level': forms.Select(attrs={
                'class': 'form-select',
            }),
            'max_capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'placeholder': _('15'),
            }),
            'fee_per_session': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'step': 0.01,
                'placeholder': _('e.g., 500.00'),
            }),
            'schedule': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('e.g., Mon/Wed 4:00-5:30 PM'),
            }),
        }
        labels = {
            'name': _('Batch Name'),
            'subject': _('Subject'),
            'grade_level': _('Grade Level'),
            'max_capacity': _('Maximum Capacity'),
            'fee_per_session': _('Fee per Session (KSh)'),
            'schedule': _('Schedule'),
        }
        help_texts = {
            'max_capacity': _('Leave at 1 if unlimited (or set a specific limit).'),
            'fee_per_session': _('Amount in Kenyan Shillings.'),
        }

    def _init_(self, *args, **kwargs):
        super()._init_(*args, **kwargs)
        # Mark required fields
        self.fields['name'].required = True
        self.fields['subject'].required = True
        self.fields['grade_level'].required = True

    def clean_name(self):
        """Ensure batch name is unique for the same teacher."""
        name = self.cleaned_data.get('name')
        teacher = self.instance.teacher if self.instance else None
        if teacher and name:
            exists = Batch.objects.filter(
                teacher=teacher,
                name__iexact=name
            ).exclude(pk=self.instance.pk if self.instance else None).exists()
            if exists:
                raise ValidationError(
                    _('You already have a batch with this name. Please choose a different name.')
                )
        return name

    def clean_max_capacity(self):
        max_capacity = self.cleaned_data.get('max_capacity')
        if max_capacity is not None and max_capacity < 1:
            raise ValidationError(_('Maximum capacity must be at least 1.'))
        return max_capacity

    def clean_fee_per_session(self):
        fee = self.cleaned_data.get('fee_per_session')
        if fee is not None and fee < 0:
            raise ValidationError(_('Fee per session cannot be negative.'))
        return fee

    def clean(self):
        """Ensure at least one of name, subject, or grade level is provided."""
        cleaned_data = super().clean()
        # All are required, so validation is already handled
        return cleaned_data


# ============================================================================
# ENROLLMENT FORM
# ============================================================================

class EnrollmentForm(forms.Form):
    """
    Form for enrolling a student into a batch.
    Supports either selecting an existing student or creating a new one.
    """
    student = forms.ModelChoiceField(
        queryset=User.objects.filter(role='student', is_active=True),
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        required=False,
        label=_('Select Existing Student'),
        help_text=_('Choose a student from the dropdown.')
    )
    create_new = forms.BooleanField(
        required=False,
        label=_('Create New Student'),
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'role': 'switch',
        }),
        help_text=_('Check this to create a new student account.')
    )
    username = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Choose a unique username'),
        }),
        label=_('Username'),
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('First name'),
        }),
        label=_('First Name'),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Last name'),
        }),
        label=_('Last Name'),
    )
    phone = forms.CharField(
        max_length=15,
        required=False,
        validators=[validate_phone],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('e.g., +254 712 345 678'),
        }),
        label=_('Phone Number'),
        help_text=_('Optional, but recommended.'),
    )

    def _init_(self, *args, **kwargs):
        super()._init_(*args, **kwargs)
        # Mark required fields (conditional validation in clean())
        self.fields['student'].required = False
        self.fields['username'].required = False
        self.fields['first_name'].required = False
        self.fields['last_name'].required = False

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        create_new = cleaned_data.get('create_new')
        username = cleaned_data.get('username')
        first_name = cleaned_data.get('first_name')
        last_name = cleaned_data.get('last_name')
        phone = cleaned_data.get('phone')

        # Validate phone if provided
        if phone:
            try:
                validate_phone(phone)
            except ValidationError as e:
                self.add_error('phone', e.message)

        if create_new:
            # Creating a new student – username, first_name, last_name are required
            if not username:
                self.add_error('username', _('Username is required when creating a new student.'))
            elif User.objects.filter(username=username).exists():
                self.add_error('username', _('This username is already taken.'))

            if not first_name:
                self.add_error('first_name', _('First name is required.'))
            if not last_name:
                self.add_error('last_name', _('Last name is required.'))

            # Optional: check for existing user with same email/phone
            if phone and User.objects.filter(phone=phone).exists():
                self.add_error('phone', _('A user with this phone number already exists.'))

        else:
            # Selecting an existing student – student field is required
            if not student:
                self.add_error('student', _('Please select a student or check "Create new student".'))

        return cleaned_data


# ============================================================================
# STUDENT QUICK CREATE FORM
# ============================================================================

class StudentQuickCreateForm(forms.ModelForm):
    """
    Form for quickly creating a new student account during enrollment.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': _('Leave blank for default'),
        }),
        required=False,
        label=_('Password'),
        help_text=_('Default password: "default123". Student can change it after login.')
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'phone']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Choose a unique username'),
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('First name'),
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Last name'),
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('e.g., +254 712 345 678'),
            }),
        }
        labels = {
            'username': _('Username'),
            'first_name': _('First Name'),
            'last_name': _('Last Name'),
            'phone': _('Phone Number'),
        }
        help_texts = {
            'username': ('Required. 150 characters or fewer. Letters, digits and @/./+/-/ only.'),
            'phone': _('Optional, but recommended.'),
        }

    def _init_(self, *args, **kwargs):
        super()._init_(*args, **kwargs)
        # Mark required fields
        self.fields['username'].required = True
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True

    def clean_username(self):
        """Ensure username is unique."""
        username = self.cleaned_data.get('username')
        if username and User.objects.filter(username=username).exists():
            raise ValidationError(_('This username is already taken. Please choose another.'))
        return username

    def clean_phone(self):
        """Validate phone number format."""
        phone = self.cleaned_data.get('phone')
        if phone:
            validate_phone(phone)
            if User.objects.filter(phone=phone).exists():
                raise ValidationError(_('A user with this phone number already exists.'))
        return phone

class LinkParentForm(forms.Form):
    parent = forms.ModelChoiceField(
        queryset=User.objects.filter(role='parent', is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Select Parent',
        help_text='Select a parent to link, or leave empty to unlink.'
    )
