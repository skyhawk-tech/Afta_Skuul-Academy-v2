from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from content.models import LessonProgress
from .models import DailyAttendanceSnapshot, StudentProgressSnapshot


@receiver(post_save, sender=LessonProgress)
def update_attendance_snapshot(sender, instance, created, **kwargs):
    """
    When a student's progress is updated, refresh the daily snapshot
    for that lesson's batch.
    """
    if instance.is_completed:
        today = timezone.now().date()
        batch = instance.lesson.batch

        # Compute the snapshot for today
        DailyAttendanceSnapshot.compute_for_batch(batch, today)

        # Also update the student's cumulative progress snapshot
        StudentProgressSnapshot.compute_for_student_batch(
            instance.student,
            batch,
            today
        )