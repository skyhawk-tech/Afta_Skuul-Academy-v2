import re
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.validators import EmailValidator
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from .models import User


# ============================================================================
# CUSTOM VALIDATORS
# ============================================================================

def validate_phone(value):
    """
    Validate that the phone number contains only digits, spaces, '+', '-' and parentheses.
    Minimum length 7, maximum 15.
    """
    if value and not re.match(r'^[\+\d\s\-\(\)]{7,15}$', value):
        raise ValidationError(
            _('Enter a valid phone number (e.g., +254 712 345 678).')
        )
    return value


def validate_tsc(value):
    """Validate TSC number format: 6–8 digits."""
    if value:
        if not value.isdigit() or not (6 <= len(value) <= 8):
            raise ValidationError(
                _('TSC number must be 6 to 8 digits (e.g., 123456).')
            )
    return value


# ============================================================================
# REGISTRATION FORM
# ============================================================================

class UserRegistrationForm(UserCreationForm):
    """
    Advanced registration form with role selection, TSC for teachers,
    email validation, and dynamic field styling.
    Prevents public registration of admin accounts.
    """
    email = forms.EmailField(
        required=True,
        validators=[EmailValidator()],
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': _('Enter your email address'),
            'autocomplete': 'email',
        }),
        label=_('Email Address'),
        help_text=_('We will send you important updates via email.')
    )
    first_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('First name'),
            'autocomplete': 'given-name',
        }),
        label=_('First Name')
    )
    last_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('Last name'),
            'autocomplete': 'family-name',
        }),
        label=_('Last Name')
    )
    phone = forms.CharField(
        required=False,
        validators=[validate_phone],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('e.g., +254 712 345 678'),
            'autocomplete': 'tel',
        }),
        label=_('Phone Number'),
        help_text=_('Optional, but recommended for parents.')
    )
    role = forms.ChoiceField(
        choices=User.ROLE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'aria-describedby': 'roleHelp',
            'id': 'id_role',
        }),
        label=_('I am a'),
        help_text=_('Select the role that best describes you.')
    )

    # ==================== TSC NUMBER (teachers only) ====================
    tsc_number = forms.CharField(
        required=False,
        max_length=20,
        validators=[validate_tsc],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('e.g., 123456'),
            'id': 'id_tsc_number',
            'autocomplete': 'off',
        }),
        label=_('TSC Number'),
        help_text=_('Required for teachers. 6–8 digits only.')
    )

    class Meta:
        model = User
        fields = (
            'username', 'email', 'first_name', 'last_name',
            'phone', 'role', 'tsc_number',   # ← added
            'password1', 'password2'
        )
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Choose a unique username'),
                'autocomplete': 'username',
            }),
        }
        labels = {
            'username': _('Username'),
        }
        help_texts = {
            'username': _(
                'Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'
            ),
        }

    # ✅ FIXED: _init_ (double underscores), not init
    def _init_(self, *args, **kwargs):
        """Initialize the form and apply Bootstrap styling to password fields."""
        super()._init_(*args, **kwargs)

        # Style password fields
        self.fields['password1'].widget = forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': _('Enter password'),
            'autocomplete': 'new-password',
        })
        self.fields['password2'].widget = forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': _('Confirm password'),
            'autocomplete': 'new-password',
        })

        # Customise help texts for password fields
        self.fields['password1'].help_text = _(
            'Your password must be at least 8 characters and not be entirely numeric.'
        )
        self.fields['password2'].help_text = _(
            'Enter the same password as before, for verification.'
        )

    def clean_email(self):
        """Ensure email is unique and properly formatted."""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError(_('A user with this email already exists.'))
        return email

    def clean_role(self):
        """Prevent public registration of admin accounts."""
        role = self.cleaned_data.get('role')
        if role == 'admin':
            raise ValidationError(
                _('Admin accounts cannot be created through registration.')
            )
        return role

    def clean_tsc_number(self):
        """Validate TSC number format and uniqueness (only meaningful for teachers)."""
        tsc = self.cleaned_data.get('tsc_number')
        if not tsc:
            return tsc

        # Format check
        if not tsc.isdigit() or not (6 <= len(tsc) <= 8):
            raise ValidationError(
                _('TSC number must be 6 to 8 digits (e.g., 123456).')
            )

        # Uniqueness check
        if User.objects.filter(tsc_number=tsc).exists():
            raise ValidationError(
                _('This TSC number is already registered.')
            )

        return tsc

    def clean(self):
        """Role-based validation (TSC required for teachers)."""
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        tsc = cleaned_data.get('tsc_number')

        if role == 'teacher' and not tsc:
            self.add_error(
                'tsc_number',
                _('TSC number is required for teachers.')
            )

        if role != 'teacher' and tsc:
            self.add_error(
                'tsc_number',
                _('TSC number can only be set for teachers.')
            )

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone = self.cleaned_data.get('phone', '')
        user.role = self.cleaned_data['role']

        # Only set TSC for teachers
        if user.role == 'teacher':
            user.tsc_number = self.cleaned_data.get('tsc_number') or None
        else:
            user.tsc_number = None

        if commit:
            user.save()
        return user


# ============================================================================
# PROFILE UPDATE FORM
# ============================================================================

class UserProfileForm(UserChangeForm):
    """
    Profile update form with enhanced fields, uniqueness validation,
    and automatic Bootstrap styling.
    Password is deliberately excluded (handled separately).
    TSC number is read-only if already set (must be edited via admin).
    """
    password = None  # Remove the password field

    class Meta:
        model = User
        fields = (
            'username', 'email', 'first_name', 'last_name',
            'phone', 'tsc_number',   # ← added
        )
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Username'),
                'autocomplete': 'username',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': _('Email address'),
                'autocomplete': 'email',
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('First name'),
                'autocomplete': 'given-name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Last name'),
                'autocomplete': 'family-name',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Phone number'),
                'autocomplete': 'tel',
            }),
            'tsc_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('e.g., 123456'),
            }),
        }

    # ✅ FIXED: _init_ (double underscores)
    def _init_(self, *args, **kwargs):
        """Initialize the profile form with custom labels and help texts."""
        super()._init_(*args, **kwargs)

        # Customise labels and help texts
        self.fields['email'].label = _('Email Address')
        self.fields['username'].help_text = _(
            'Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'
        )

        # TSC field: only show for teachers
        user = self.instance
        if user and user.role != 'teacher':
            # Non-teachers shouldn't see the TSC field at all
            self.fields.pop('tsc_number', None)
        elif user and user.tsc_number:
            # Once set, TSC can't be edited by the user (only by admin)
            self.fields['tsc_number'].disabled = True
            self.fields['tsc_number'].help_text = _(
                'TSC number cannot be changed. Contact admin if needed.'
            )
        else:
            # Teacher without TSC yet — required
            self.fields['tsc_number'].required = True
            self.fields['tsc_number'].validators = [validate_tsc]

    def clean_email(self):
        """Ensure email is unique, but allow the current user to keep their email."""
        email = self.cleaned_data.get('email')
        if self.instance and self.instance.email == email:
            return email
        if User.objects.exclude(pk=self.instance.pk).filter(email=email).exists():
            raise ValidationError(
                _('This email is already in use by another account.')
            )
        return email

    def clean_username(self):
        """Ensure username is unique, allowing the current user to keep theirs."""
        username = self.cleaned_data.get('username')
        if self.instance and self.instance.username == username:
            return username
        if User.objects.exclude(pk=self.instance.pk).filter(username=username).exists():
            raise ValidationError(
                _('A user with that username already exists.')
            )
        return username

    def clean_phone(self):
        """Validate phone number format (optional)."""
        phone = self.cleaned_data.get('phone')
        if phone:
            validate_phone(phone)
        return phone

    def clean_tsc_number(self):
        """Ensure TSC number is unique (if present)."""
        tsc = self.cleaned_data.get('tsc_number')
        if not tsc:
            return tsc

        # Format check
        if not tsc.isdigit() or not (6 <= len(tsc) <= 8):
            raise ValidationError(
                _('TSC number must be 6 to 8 digits (e.g., 123456).')
            )

        # Uniqueness check (excluding the current user)
        if User.objects.exclude(pk=self.instance.pk).filter(tsc_number=tsc).exists():
            raise ValidationError(
                _('This TSC number is already in use by another teacher.')
            )

        return tsc