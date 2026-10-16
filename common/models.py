from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError


class TimeStampedModel(models.Model):
    """
    Abstract base model with created_at and updated_at timestamps.

    Features:
    - Automatic timestamp tracking
    - Custom manager with date filtering methods
    - Helper methods for date checks
    - Database indexing for performance

    Usage:
        class MyModel(TimeStampedModel):
            name = models.CharField(max_length=100)
    """
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='Created At',
        help_text='The timestamp when this record was created.'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
        verbose_name='Updated At',
        help_text='The timestamp when this record was last updated.'
    )

    objects = models.Manager()

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def _str_(self):
        """Default string representation for timestamped models."""
        return f"{self._class.name_} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    def is_created_today(self) -> bool:
        """Return True if the record was created today."""
        return self.created_at.date() == timezone.now().date()

    def is_created_within(self, days: int = 7) -> bool:
        """Return True if the record was created within the specified number of days."""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.created_at >= cutoff

    def was_updated_within(self, days: int = 7) -> bool:
        """Return True if the record was updated within the specified number of days."""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.updated_at >= cutoff

    @classmethod
    def created_between(cls, start_date, end_date):
        """Return records created between two dates."""
        return cls.objects.filter(created_at_dategte=start_date, created_atdate_lte=end_date)

    @classmethod
    def created_today(cls):
        """Return records created today."""
        today = timezone.now().date()
        return cls.objects.filter(created_at__date=today)


class TimeStampedModelManager(models.Manager):
    """
    Custom manager for TimeStampedModel with additional query methods.
    """
    def active(self):
        """Return only active records (if the model has an is_active field)."""
        return self.filter(is_active=True)

    def created_today(self):
        """Return records created today."""
        today = timezone.now().date()
        return self.filter(created_at__date=today)

    def created_within(self, days: int = 7):
        """Return records created within the specified number of days."""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.filter(created_at__gte=cutoff)

    def updated_within(self, days: int = 7):
        """Return records updated within the specified number of days."""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.filter(updated_at__gte=cutoff)


class SoftDeleteModelManager(models.Manager):
    """
    Manager for SoftDeleteModel that excludes deleted records by default.
    """
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def deleted(self):
        """Return only deleted records."""
        return super().get_queryset().filter(deleted_at__isnull=False)

    def all_with_deleted(self):
        """Return all records including deleted ones."""
        return super().get_queryset()


class SoftDeleteModel(models.Model):
    """
    Abstract model that adds soft delete functionality.

    Features:
    - deleted_at timestamp instead of permanent deletion
    - Custom manager that excludes deleted records by default
    - Methods to restore or permanently delete

    Usage:
        class MyModel(SoftDeleteModel):
            name = models.CharField(max_length=100)
    """
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='Deleted At',
        help_text='The timestamp when this record was soft deleted.'
    )

    objects = SoftDeleteModelManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """
        Override delete to perform soft delete instead of permanent deletion.
        """
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at'])

    def hard_delete(self, using=None, keep_parents=False):
        """
        Permanently delete the record from the database.
        """
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """
        Restore a soft-deleted record.
        """
        self.deleted_at = None
        self.save(update_fields=['deleted_at'])

    @property
    def is_deleted(self) -> bool:
        """Return True if the record is soft deleted."""
        return self.deleted_at is not None


class AuditModel(models.Model):
    """
    Abstract model that tracks who created and updated records.

    Features:
    - created_by and updated_by foreign keys to User
    - Automatically populates on save
    - Helper methods to check ownership

    Usage:
        class MyModel(AuditModel):
            name = models.CharField(max_length=100)

    Note: Requires a custom save method in your view or a signal.
    """
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_created',
        verbose_name='Created By',
        help_text='The user who created this record.'
    )
    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_updated',
        verbose_name='Updated By',
        help_text='The user who last updated this record.'
    )

    class Meta:
        abstract = True

    def is_created_by(self, user) -> bool:
        """Return True if the record was created by the given user."""
        return self.created_by == user

    def is_updated_by(self, user) -> bool:
        """Return True if the record was last updated by the given user."""
        return self.updated_by == user


class VersionedModel(models.Model):
    """
    Abstract model that tracks the version number of a record.

    Features:
    - version field that auto-increments on each save
    - Useful for tracking changes and optimistic locking

    Usage:
        class MyModel(VersionedModel):
            name = models.CharField(max_length=100)
    """
    version = models.PositiveIntegerField(
        default=1,
        editable=False,
        verbose_name='Version',
        help_text='The version number of this record.'
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Increment version on each save."""
        if self.pk:
            # If updating, increment version
            self.version += 1
        super().save(*args, **kwargs)


# ============================================================================
# COMBINED MIXINS FOR COMMON USE CASES
# ============================================================================

class BaseModel(TimeStampedModel, SoftDeleteModel):
    """
    A comprehensive base model that includes:
    - Timestamps (created_at, updated_at)
    - Soft delete (deleted_at)
    - Indexed fields for performance
    """
    class Meta:
        abstract = True
        ordering = ['-created_at']


class AuditBaseModel(TimeStampedModel, SoftDeleteModel, AuditModel):
    """
    A comprehensive base model that includes:
    - Timestamps (created_at, updated_at)
    - Soft delete (deleted_at)
    - Audit tracking (created_by, updated_by)
    """
    class Meta:
        abstract = True
        ordering = ['-created_at']