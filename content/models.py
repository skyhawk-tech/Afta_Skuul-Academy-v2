import uuid

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.urls import reverse

from accounts.models import User


class Lesson(models.Model):
    """A recorded video lesson OR a live class for a batch."""

    # ==================== BATCH ====================
    batch = models.ForeignKey(
        'batches.Batch',
        on_delete=models.CASCADE,
        related_name='lessons',
        db_index=True,
    )

    # ==================== BASIC INFO ====================
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    chapter = models.CharField(max_length=100, blank=True)
    part_number = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)]
    )

    # ==================== LESSON TYPE ====================
    LESSON_TYPES = (
        ('recorded', 'Recorded Video'),
        ('live', 'Live Class'),
    )
    lesson_type = models.CharField(
        max_length=10,
        choices=LESSON_TYPES,
        default='recorded',
        help_text='Is this a recorded video or a live class?'
    )

    # ==================== RECORDED VIDEO FIELDS ====================
    video_file = models.FileField(
        upload_to='videos/%Y/%m/%d/',
        blank=True,
        null=True,
    )
    video_url = models.URLField(blank=True, null=True)
    video_duration = models.PositiveIntegerField(
        default=0,
        help_text='Duration in seconds.'
    )

    # ==================== LIVE CLASS FIELDS ====================
    live_room_name = models.CharField(
        max_length=100,
        blank=True,
        help_text='Auto-generated unique room ID for live lessons.'
    )
    live_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When does the live class start?'
    )
    live_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When does the live class end?'
    )
    # Minimum seconds a student must attend to be counted as "attended"
    live_min_attendance_seconds = models.PositiveIntegerField(
        default=600,
        help_text='Minimum seconds to count as attended (default: 10 minutes).'
    )

    # ==================== SUPPLEMENTARY ====================
    notes_file = models.FileField(
        upload_to='notes/%Y/%m/%d/',
        blank=True,
        null=True,
    )

    # ==================== DISPLAY & COMPLETION ====================
    order = models.PositiveIntegerField(default=0)
    required_watch_percentage = models.PositiveIntegerField(
        default=80,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    # ==================== SCHEDULING ====================
    release_date = models.DateTimeField(null=True, blank=True)

    # ==================== TIMESTAMPS ====================
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'chapter', 'part_number', 'created_at']
        indexes = [
            models.Index(fields=['batch', 'order']),
            models.Index(fields=['batch', 'chapter', 'part_number']),
            models.Index(fields=['release_date']),
            models.Index(fields=['lesson_type', 'live_start']),
        ]

    def _str_(self):
        if self.chapter:
            return f"{self.batch.name} – {self.chapter} (Part {self.part_number})"
        return f"{self.batch.name} – {self.title}"

    def get_absolute_url(self):
        return reverse('content:lesson_detail', kwargs={'lesson_id': self.id})

    # ==================== BASIC PROPERTIES ====================
    @property
    def is_released(self):
        if self.release_date:
            return timezone.now() >= self.release_date
        return True

    @property
    def duration_formatted(self):
        seconds = self.video_duration or 0
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if secs or not parts:
            parts.append(f"{secs}s")
        return " ".join(parts)

    # ==================== LIVE CLASS PROPERTIES ====================
    @property
    def is_live_now(self):
        """Return True if the live class is currently running."""
        if self.lesson_type != 'live':
            return False
        if not self.live_start or not self.live_end:
            return False
        now = timezone.now()
        return self.live_start <= now <= self.live_end

    @property
    def has_ended(self):
        """Return True if the live class has finished."""
        if self.lesson_type != 'live' or not self.live_end:
            return False
        return timezone.now() > self.live_end

    @property
    def starts_in_minutes(self):
        """Return minutes until class starts."""
        if self.lesson_type != 'live' or not self.live_start:
            return None
        delta = self.live_start - timezone.now()
        return max(0, int(delta.total_seconds() / 60))

    @property
    def scheduled_minutes(self):
        """Return scheduled live class duration in minutes."""
        if not self.live_start or not self.live_end:
            return 0
        return int((self.live_end - self.live_start).total_seconds() / 60)

    # ==================== LIVE ATTENDANCE AGGREGATES ====================
    @property
    def live_attendees(self):
        """
        Return LessonProgress records for students who attended this live class
        (i.e., accumulated at least 1 second of attendance).
        """
        if self.lesson_type != 'live':
            return LessonProgress.objects.none()

        return LessonProgress.objects.filter(
            lesson=self,
            total_watch_seconds__gt=0
        ).select_related('student').order_by('-total_watch_seconds')

    @property
    def live_attended_count(self):
        """Number of students who joined this live class."""
        return self.live_attendees.count()

    @property
    def live_enrolled_count(self):
        """Number of active students in the batch."""
        return self.batch.enrollments.filter(is_active=True).count()

    @property
    def live_attendance_rate(self):
        """Attendance percentage for a live class."""
        total = self.live_enrolled_count
        if total == 0:
            return 0
        return round((self.live_attended_count / total) * 100, 1)

    # ==================== VALIDATION ====================
    def clean(self):
        # Recorded lessons need a video source
        if self.lesson_type == 'recorded':
            if not self.video_file and not self.video_url:
                raise ValidationError(
                    'Recorded lessons must have either a video file or a video URL.'
                )

        # Live lessons need start & end times
        if self.lesson_type == 'live':
            if not self.live_start or not self.live_end:
                raise ValidationError(
                    'Live lessons must have a start and end time.'
                )
            if self.live_end <= self.live_start:
                raise ValidationError(
                    {'live_end': 'End time must be after start time.'}
                )

        # Release date cannot be in the past
        if self.release_date and self.release_date < timezone.now():
            raise ValidationError(
                {'release_date': 'Release date cannot be in the past.'}
            )

    # ==================== SAVE ====================
    def save(self, *args, **kwargs):
        # Auto-generate a Jitsi room name for live lessons
        if self.lesson_type == 'live' and not self.live_room_name:
            self.live_room_name = f"skuul-{self.batch_id}-{uuid.uuid4().hex[:12]}"

        self.full_clean()
        super().save(*args, **kwargs)


class LessonProgress(models.Model):
    """Tracks a student's watch progress for a lesson (recorded or live)."""

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='lesson_progress',
        db_index=True,
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='progress',
        db_index=True,
    )

    total_watch_seconds = models.PositiveIntegerField(default=0)
    last_position = models.PositiveIntegerField(default=0)
    watch_percentage = models.FloatField(default=0.0)
    is_completed = models.BooleanField(default=False)

    first_watch = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'lesson')
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['student', 'lesson']),
            models.Index(fields=['is_completed']),
        ]

    def _str_(self):
        return (
            f"{self.student.get_full_name()} – {self.lesson.title} "
            f"({self.watch_percentage:.1f}%)"
        )

    # ==================== RECORDED VIDEO PROGRESS ====================
    def update_progress(self, new_position: int):
        """
        Update watch progress based on video playback position.
        Only accumulates forward progress; rewinds update position but don't add time.
        """
        if new_position < 0:
            return

        if new_position > self.last_position:
            delta = new_position - self.last_position
            self.total_watch_seconds += delta
            self.last_position = new_position
        else:
            self.last_position = new_position

        duration = self.lesson.video_duration
        if duration > 0:
            self.watch_percentage = (self.total_watch_seconds / duration) * 100
            self.is_completed = (
                self.watch_percentage >= self.lesson.required_watch_percentage
            )
        else:
            self.watch_percentage = 0.0
            self.is_completed = False

        self.save(update_fields=[
            'total_watch_seconds', 'last_position',
            'watch_percentage', 'is_completed', 'last_activity'
        ])

    # ==================== LIVE CLASS ATTENDANCE ====================
    def add_live_time(self, seconds: int):
        """
        Add elapsed seconds to a student's live-class attendance.
        Called from the live class heartbeat endpoint (every 60 seconds).

        - Accumulates attendance time.
        - Marks completed once the student reaches
          lesson.live_min_attendance_seconds (default: 600 = 10 minutes).
        - Computes watch_percentage against the scheduled class duration.
        """
        if seconds <= 0:
            return

        self.total_watch_seconds += seconds

        # Completion threshold for live classes
        min_seconds = self.lesson.live_min_attendance_seconds or 600
        if self.total_watch_seconds >= min_seconds:
            self.is_completed = True

        # Calculate watch percentage vs scheduled duration
        if self.lesson.live_start and self.lesson.live_end:
            scheduled = (
                self.lesson.live_end - self.lesson.live_start
            ).total_seconds()
            if scheduled > 0:
                self.watch_percentage = min(
                    100.0,
                    (self.total_watch_seconds / scheduled) * 100
                )
        else:
            # Fallback: percentage against minimum attendance threshold
            if min_seconds > 0:
                self.watch_percentage = min(
                    100.0,
                    (self.total_watch_seconds / min_seconds) * 100
                )

        self.save(update_fields=[
            'total_watch_seconds',
            'watch_percentage',
            'is_completed',
            'last_activity',
        ])

    # ==================== DISPLAY HELPERS ====================
    @property
    def attended_minutes(self):
        """Total attendance in minutes (rounded)."""
        return round((self.total_watch_seconds or 0) / 60, 1)

    @property
    def attendance_status(self):
        """Return a friendly status string for the UI."""
        if self.total_watch_seconds == 0:
            return 'not_started'
        if self.is_completed:
            return 'completed'
        return 'in_progress'


class LessonQuestion(models.Model):
    """A student's question about a lesson. Visible to the whole batch."""

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='questions',
        db_index=True,
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='asked_questions',
        db_index=True,
    )
    body = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lesson', 'created_at']),
            models.Index(fields=['is_resolved']),
        ]

    def _str_(self):
        return f"{self.student.get_full_name()} – {self.body[:50]}"

    @property
    def reply_count(self):
        return self.replies.count()

    @property
    def teacher_replied(self):
        return self.replies.filter(author__role='teacher').exists()


class LessonReply(models.Model):
    """A reply to a lesson question – by a teacher or another student."""

    question = models.ForeignKey(
        LessonQuestion,
        on_delete=models.CASCADE,
        related_name='replies',
        db_index=True,
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='lesson_replies',
        db_index=True,
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def _str_(self):
        return f"{self.author.get_full_name()} → {self.question.body[:30]}"

    @property
    def is_teacher_reply(self):
        return self.author.role == 'teacher'