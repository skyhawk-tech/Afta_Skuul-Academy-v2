from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.urls import reverse

from accounts.models import User


class ActiveBatchManager(models.Manager):
    """
    Manager that only returns active batches.
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class Batch(models.Model):
    """
    A tuition batch/class taught by a teacher.
    """
    GRADE_CHOICES = (
        ('PP1', 'PP1'),
        ('PP2', 'PP2'),
        ('PP3', 'PP3'),
        ('Grade 1', 'Grade 1'),
        ('Grade 2', 'Grade 2'),
        ('Grade 3', 'Grade 3'),
        ('Grade 4', 'Grade 4'),
        ('Grade 5', 'Grade 5'),
        ('Grade 6', 'Grade 6'),
        ('Grade 7', 'Grade 7'),
        ('Grade 8', 'Grade 8'),
        ('Grade 9', 'Grade 9'),
    )

    # Core fields
    name = models.CharField(
        max_length=100,
        help_text="e.g., 'Math G4 - Mon/Wed'"
    )
    subject = models.CharField(
        max_length=50,
        help_text="Subject name (e.g., Mathematics, English, Science)"
    )
    grade_level = models.CharField(
        max_length=10,
        choices=GRADE_CHOICES,
        db_index=True,
        help_text="The grade level this batch is for."
    )

    # Teacher relationship (foreign key)
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='batches',
        db_index=True,
    )

    # Capacity and fees
    max_capacity = models.PositiveIntegerField(
        default=15,
        validators=[MinValueValidator(1)],
        help_text="Maximum number of students allowed."
    )
    fee_per_session = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Fee per session in KSh."
    )

    # Status and schedule
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Uncheck to archive this batch."
    )
    schedule = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g., 'Mon/Wed 4:00-5:30 PM'"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom managers
    objects = models.Manager()  # Default manager
    active = ActiveBatchManager()  # Returns only active batches

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Batch'
        verbose_name_plural = 'Batches'
        indexes = [
            models.Index(fields=['teacher', 'grade_level']),
            models.Index(fields=['subject', 'grade_level']),
            models.Index(fields=['is_active', 'created_at']),
        ]

    def _str_(self):
        return f"{self.subject} - {self.grade_level} ({self.teacher.get_full_name()})"

    def get_absolute_url(self):
        """Return the URL to view this batch (teacher detail)."""
        return reverse('batches:batch_detail', kwargs={'batch_id': self.id})

    @property
    def student_count(self):
        """Return the number of active enrolled students."""
        return self.enrollments.filter(is_active=True).count()

    @property
    def available_slots(self):
        """Return the number of available slots."""
        if self.max_capacity:
            return self.max_capacity - self.student_count
        return None

    @property
    def is_full(self):
        """Return True if the batch is at capacity."""
        if self.max_capacity:
            return self.student_count >= self.max_capacity
        return False

    def clean(self):
        """
        Validate the batch data.
        """
        # Prevent negative fees
        if self.fee_per_session is not None and self.fee_per_session < 0:
            raise ValidationError({'fee_per_session': 'Fee cannot be negative.'})

        # Ensure max_capacity is at least 1
        if self.max_capacity is not None and self.max_capacity < 1:
            raise ValidationError({'max_capacity': 'Capacity must be at least 1.'})

        # Ensure teacher is actually a teacher
        if self.teacher and self.teacher.role != 'teacher':
            raise ValidationError({'teacher': 'The selected user must be a teacher.'})

    def save(self, *args, **kwargs):
        """Override save to run validation before saving."""
        self.full_clean()
        super().save(*args, **kwargs)


class EnrollmentManager(models.Manager):
    """
    Custom manager for Enrollment model.
    """
    def active(self):
        """Return only active enrollments."""
        return self.filter(is_active=True)

    def for_student(self, student):
        """Return enrollments for a specific student."""
        return self.filter(student=student)

    def for_teacher(self, teacher):
        """Return enrollments for all batches taught by a teacher."""
        return self.filter(batch__teacher=teacher)


class Enrollment(models.Model):
    """
    Student enrollment in a batch.
    """
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='enrollments',
        db_index=True,
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name='enrollments',
        db_index=True,
    )
    enrolled_on = models.DateTimeField(auto_now_add=True, db_index=True)
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Uncheck to unenroll the student."
    )

    # Custom manager
    objects = EnrollmentManager()

    class Meta:
        unique_together = ('student', 'batch')
        ordering = ['-enrolled_on']
        verbose_name = 'Enrollment'
        verbose_name_plural = 'Enrollments'
        indexes = [
            models.Index(fields=['student', 'is_active']),
            models.Index(fields=['batch', 'is_active']),
        ]

    def _str_(self):
        return f"{self.student.get_full_name()} → {self.batch.name}"

    def get_absolute_url(self):
        """Return the URL to view this enrollment (batch detail)."""
        return reverse('batches:batch_detail', kwargs={'batch_id': self.batch.id})

    def clean(self):
        """
        Validate the enrollment data.
        """
        # Ensure student is actually a student
        if self.student and self.student.role != 'student':
            raise ValidationError({'student': 'The selected user must be a student.'})

        # Check if batch is full (only on creation, not on update if already enrolled)
        if not self.pk and self.batch and self.batch.is_full:
            raise ValidationError('This batch is already at full capacity.')

    def save(self, *args, **kwargs):
        """Override save to run validation before saving."""
        self.full_clean()
        super().save(*args, **kwargs)
        
