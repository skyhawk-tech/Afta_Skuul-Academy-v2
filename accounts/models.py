from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator


class UserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError('The Username field must be set')
        email = self.normalize_email(email)
        extra_fields.setdefault('role', 'student')
        extra_fields.setdefault('is_active', True)

        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
        ('parent', 'Parent'),
    )

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    phone = models.CharField(max_length=15, blank=True)
    subjects = models.CharField(
        max_length=200,
        blank=True,
        help_text="Comma separated subjects (for teachers)"
    )
    is_active = models.BooleanField(default=True)

    # ==================== TSC NUMBER (for teachers) ====================
    tsc_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="TSC registration number (required for teachers only).",
        validators=[
            RegexValidator(
                regex=r'^\d{6,8}$',
                message='TSC number must be 6 to 8 digits.',
            )
        ],
    )

    # ==================== PARENT ↔️ CHILD LINK ====================
    children = models.ManyToManyField(
        'self',
        symmetrical=False,
        blank=True,
        limit_choices_to={'role': 'student'},
        related_name='parents'
    )

    # ==================== AVOID CLASHES WITH DJANGO AUTH ====================
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='accounts_user_set',
        blank=True,
        verbose_name='groups',
        help_text='The groups this user belongs to.'
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='accounts_user_permissions_set',
        blank=True,
        verbose_name='user permissions',
        help_text='Specific permissions for this user.'
    )

    objects = UserManager()

    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def _str_(self):
        full_name = self.get_full_name()
        if full_name:
            return f"{full_name} ({self.role})"
        return f"{self.username} ({self.role})"

    def clean(self):
        """Validate role-specific requirements."""
        super().clean()

        # Superusers must be admins
        if self.is_superuser and self.role != 'admin':
            raise ValidationError('Superusers must have role="admin".')

        # Teachers must have at least one subject
        if self.role == 'teacher' and not self.subjects:
            raise ValidationError({
                'subjects': 'Teachers must specify at least one subject.'
            })

        # Teachers must have a TSC number
        if self.role == 'teacher' and not self.tsc_number:
            raise ValidationError({
                'tsc_number': 'TSC number is required for teachers.'
            })

        # Non-teachers should not have a TSC number
        if self.role != 'teacher' and self.tsc_number:
            raise ValidationError({
                'tsc_number': 'TSC number can only be set for teachers.'
            })