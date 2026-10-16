from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.urls import reverse

from batches.models import Batch
from content.models import Lesson
from accounts.models import User


class AssignmentManager(models.Manager):
    """
    Custom manager for Assignment model.
    """
    def for_teacher(self, teacher):
        """Return assignments for all batches taught by a specific teacher."""
        return self.filter(batch__teacher=teacher)

    def for_student(self, student):
        """Return assignments for batches a student is enrolled in."""
        return self.filter(batch_enrollmentsstudent=student, batchenrollments_is_active=True)

    def overdue(self):
        """Return assignments where the due date has passed."""
        return self.filter(due_date__lt=timezone.now())

    def upcoming(self):
        """Return assignments due in the future."""
        return self.filter(due_date__gte=timezone.now())


class Assignment(models.Model):
    """
    An assignment (exercise or exam) for a batch.
    Questions are stored as a JSON list for flexibility.
    """
    ASSIGNMENT_TYPES = (
        ('exercise', 'Exercise'),
        ('exam', 'Exam'),
    )

    # Core fields
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name='assignments',
        db_index=True,
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=10, choices=ASSIGNMENT_TYPES, default='exercise')

    # Grading and timing
    total_marks = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    due_date = models.DateTimeField(db_index=True)
    time_limit_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional time limit for exams (in minutes)."
    )

    # Questions stored as JSON:
    # [
    #   {"id": 1, "type": "mcq", "question": "...", "options": ["A", "B", "C"], "answer": "A", "marks": 1},
    #   {"id": 2, "type": "short", "question": "...", "marks": 2},
    #   {"id": 3, "type": "file", "question": "Upload your essay"}
    # ]
    questions = models.JSONField(
        default=list,
        help_text="JSON list of question objects."
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects = AssignmentManager()

    class Meta:
        ordering = ['-due_date']
        verbose_name = 'Assignment'
        verbose_name_plural = 'Assignments'
        indexes = [
            models.Index(fields=['batch', 'due_date']),
            models.Index(fields=['type', 'due_date']),
        ]

    def _str_(self):
        return f"{self.batch.name} - {self.title}"

    def get_absolute_url(self):
        """Return the URL to view this assignment."""
        return reverse('assignments:assignment_detail', kwargs={'assignment_id': self.id})

    @property
    def is_overdue(self):
        """Return True if the assignment due date has passed."""
        return timezone.now() > self.due_date

    @property
    def total_questions(self):
        """Return the total number of questions."""
        return len(self.questions)

    @property
    def mcq_count(self):
        """Return the number of MCQ questions."""
        return sum(1 for q in self.questions if q.get('type') == 'mcq')

    @property
    def total_mcq_marks(self):
        """Return the total marks available from MCQ questions."""
        return sum(
            q.get('marks', 1) for q in self.questions if q.get('type') == 'mcq'
        )

    def get_submission_for_student(self, student):
        """
        Return the submission object for a given student, or None.
        """
        try:
            return self.submissions.get(student=student)
        except Submission.DoesNotExist:
            return None

    def clean(self):
        """Validate the assignment data."""
        # Prevent due date in the past
        if self.due_date and self.due_date < timezone.now():
            raise ValidationError({'due_date': 'Due date cannot be in the past.'})

        # Validate questions structure
        if self.questions:
            for i, q in enumerate(self.questions):
                if 'id' not in q:
                    raise ValidationError({'questions': f'Question {i+1} has no ID.'})
                if 'type' not in q:
                    raise ValidationError({'questions': f'Question {i+1} has no type.'})
                if q['type'] not in ['mcq', 'short', 'file']:
                    raise ValidationError(
                        {'questions': f'Question {i+1} has invalid type: {q["type"]}.'}
                    )
                if q['type'] == 'mcq':
                    if 'options' not in q or not q['options']:
                        raise ValidationError(
                            {'questions': f'MCQ question {i+1} must have options.'}
                        )
                    if 'answer' not in q:
                        raise ValidationError(
                            {'questions': f'MCQ question {i+1} must have an answer.'}
                        )

    def save(self, *args, **kwargs):
        """Override save to run validation before saving."""
        self.full_clean()
        super().save(*args, **kwargs)


class SubmissionManager(models.Manager):
    """
    Custom manager for Submission model.
    """
    def for_teacher(self, teacher):
        """Return submissions for assignments in batches taught by a teacher."""
        return self.filter(assignment_batch_teacher=teacher)

    def for_student(self, student):
        """Return all submissions for a specific student."""
        return self.filter(student=student)

    def graded(self):
        """Return submissions that have been graded."""
        return self.filter(marks_obtained__isnull=False)

    def ungraded(self):
        """Return submissions that have not been graded."""
        return self.filter(marks_obtained__isnull=True)

    def late(self):
        """Return submissions that were submitted after the due date."""
        return self.filter(submitted_at_gt=models.F('assignment_due_date'))


class Submission(models.Model):
    """
    A student's submission for an assignment.
    """
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='submissions',
        db_index=True,
    )
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions',
        db_index=True,
    )

    # Submission content
    file_upload = models.FileField(
        upload_to='submissions/%Y/%m/%d/',
        null=True,
        blank=True,
        help_text="Upload a file (photo, PDF, etc.) for the assignment.",
    )
    # Answers stored as JSON: {"1": "A", "2": "text answer", "3": null}
    answers = models.JSONField(
        default=dict,
        help_text="Answers keyed by question ID."
    )

    # Timestamp
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Grading
    marks_obtained = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role__in': ['admin', 'teacher']},
        related_name='graded_submissions',
    )
    graded_at = models.DateTimeField(null=True, blank=True)
    is_auto_graded = models.BooleanField(default=False)

    # Custom manager
    objects = SubmissionManager()

    class Meta:
        unique_together = ('student', 'assignment')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['student', 'assignment']),
            models.Index(fields=['submitted_at']),
            models.Index(fields=['assignment', 'graded_by']),
        ]

    def _str_(self):
        return f"{self.student.get_full_name()} - {self.assignment.title}"

    def get_absolute_url(self):
        """Return the URL to view this submission."""
        return reverse('assignments:assignment_detail', kwargs={'assignment_id': self.assignment.id})

    @property
    def is_late(self):
        """Return True if submitted after the due date."""
        return self.submitted_at > self.assignment.due_date

    @property
    def is_graded(self):
        """Return True if the submission has been graded."""
        return self.marks_obtained is not None

    @property
    def grade_percentage(self):
        """Return the grade as a percentage."""
        if self.marks_obtained is not None and self.assignment.total_marks:
            return (self.marks_obtained / self.assignment.total_marks) * 100
        return None

    def get_answer_for_question(self, question_id):
        """
        Return the answer for a specific question ID.
        """
        return self.answers.get(str(question_id))

    def auto_grade_mcq(self, save=True):
        """
        Automatically grade MCQ questions.
        Supports per-question marks from the 'marks' field (defaults to 1).
        If save=True, save the submission after grading.
        Returns the total marks earned.
        """
        if not self.assignment.questions:
            return 0

        total = 0
        for q in self.assignment.questions:
            if q.get('type') == 'mcq' and 'answer' in q:
                student_answer = self.answers.get(str(q['id']))
                if student_answer == q['answer']:
                    total += q.get('marks', 1)

        # Cap to total_marks
        total = min(total, self.assignment.total_marks)
        self.marks_obtained = total
        self.is_auto_graded = True
        self.graded_at = timezone.now()

        if save:
            self.save(update_fields=['marks_obtained', 'is_auto_graded', 'graded_at'])
        return total

    def save(self, *args, **kwargs):
        """
        Override save to auto-grade MCQ-only assignments.
        """
        # Auto-grade if marks not set and all questions are MCQ
        if self.marks_obtained is None and self.assignment.questions:
            all_mcq = all(q.get('type') == 'mcq' for q in self.assignment.questions)
            if all_mcq:
                # Grade without immediate save to avoid recursion
                self.auto_grade_mcq(save=False)

        super().save(*args, **kwargs)