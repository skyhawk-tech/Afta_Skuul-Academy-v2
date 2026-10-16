from django.db import models
from django.db.models import Avg, Count, Q, Prefetch
from django.utils import timezone
from django.core.exceptions import ValidationError

from batches.models import Batch, Enrollment
from content.models import Lesson, LessonProgress
from assignments.models import Submission
from accounts.models import User


class DailyAttendanceSnapshot(models.Model):
    """
    Pre‑computed daily attendance summary per batch.
    Updated by signals, management command, or on‑demand.
    This reduces expensive real‑time aggregation queries on dashboards.
    """
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name='attendance_snapshots',
        db_index=True,
    )
    date = models.DateField(db_index=True)
    total_enrolled = models.PositiveIntegerField()
    attended_count = models.PositiveIntegerField()
    attendance_percentage = models.FloatField()
    average_watch_percentage = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('batch', 'date')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['batch', 'date']),
            models.Index(fields=['date']),
        ]

    def _str_(self):
        return f"{self.batch.name} - {self.date}: {self.attendance_percentage:.1f}%"

    @classmethod
    def compute_for_batch(cls, batch, date=None, use_release_date=False):
        """
        Compute and save a snapshot for a given batch and date.

        Args:
            batch: The Batch instance.
            date: Optional date (defaults to today).
            use_release_date: If True, use lesson.release_date instead of created_at.

        Returns:
            DailyAttendanceSnapshot: The created/updated snapshot.
        """
        if date is None:
            date = timezone.now().date()

        # Determine which date field to filter by
        date_field = 'release_date' if use_release_date else 'created_at'
        lessons = Lesson.objects.filter(
            batch=batch,
            **{f'{date_field}__date': date}
        )

        total_enrolled = Enrollment.objects.filter(batch=batch, is_active=True).count()

        if total_enrolled == 0:
            attended_count = 0
            avg_watch = 0
        else:
            # Students who completed at least one lesson on this date
            attended_count = LessonProgress.objects.filter(
                lesson__in=lessons,
                is_completed=True
            ).values('student').distinct().count()

            # Average watch percentage across all progress records for this date
            avg_watch = LessonProgress.objects.filter(
                lesson__in=lessons
            ).aggregate(avg=Avg('watch_percentage'))['avg'] or 0

        attendance_percentage = (attended_count / total_enrolled * 100) if total_enrolled else 0

        snapshot, _ = cls.objects.update_or_create(
            batch=batch,
            date=date,
            defaults={
                'total_enrolled': total_enrolled,
                'attended_count': attended_count,
                'attendance_percentage': round(attendance_percentage, 2),
                'average_watch_percentage': round(avg_watch, 2),
            }
        )
        return snapshot

    @classmethod
    def compute_for_all_batches(cls, date=None):
        """Compute snapshots for all active batches."""
        if date is None:
            date = timezone.now().date()
        batches = Batch.objects.filter(is_active=True)
        results = []
        for batch in batches:
            results.append(cls.compute_for_batch(batch, date))
        return results


class StudentProgressSnapshot(models.Model):
    """
    Cumulative progress per student per batch – updated weekly or on demand.
    Used for parent dashboards and student progress tracking.
    """
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='progress_snapshots',
        db_index=True,
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name='student_progress_snapshots',
        db_index=True,
    )
    snapshot_date = models.DateField(db_index=True)
    total_lessons = models.PositiveIntegerField(default=0)
    total_lessons_completed = models.PositiveIntegerField(default=0)
    completion_percentage = models.FloatField(default=0.0)
    average_grade = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'batch', 'snapshot_date')
        ordering = ['-snapshot_date']
        indexes = [
            models.Index(fields=['student', 'batch', 'snapshot_date']),
            models.Index(fields=['snapshot_date']),
        ]

    def _str_(self):
        return f"{self.student.get_full_name()} - {self.batch.name} ({self.snapshot_date})"

    @classmethod
    def compute_for_student_batch(cls, student, batch, date=None):
        """
        Compute and save a progress snapshot for a student in a batch.

        Args:
            student: The User instance (must have role='student').
            batch: The Batch instance.
            date: Optional date (defaults to today).

        Returns:
            StudentProgressSnapshot: The created/updated snapshot.
        """
        if date is None:
            date = timezone.now().date()

        lessons = Lesson.objects.filter(batch=batch)
        total = lessons.count()

        if total == 0:
            completed = 0
            completion = 0.0
        else:
            completed = LessonProgress.objects.filter(
                student=student,
                lesson__in=lessons,
                is_completed=True
            ).count()
            completion = (completed / total) * 100

        # Calculate average grade from submissions
        submissions = Submission.objects.filter(
            student=student,
            assignment__batch=batch,
            marks_obtained__isnull=False
        )
        avg_grade = submissions.aggregate(avg=Avg('marks_obtained'))['avg'] or 0

        snapshot, _ = cls.objects.update_or_create(
            student=student,
            batch=batch,
            snapshot_date=date,
            defaults={
                'total_lessons': total,
                'total_lessons_completed': completed,
                'completion_percentage': round(completion, 2),
                'average_grade': round(avg_grade, 2),
            }
        )
        return snapshot

    @classmethod
    def compute_for_batch_all_students(cls, batch, date=None):
        """Compute progress snapshots for all students in a batch."""
        if date is None:
            date = timezone.now().date()
        enrollments = batch.enrollments.filter(is_active=True).select_related('student')
        results = []
        for enrollment in enrollments:
            results.append(cls.compute_for_student_batch(enrollment.student, batch, date))
        return results