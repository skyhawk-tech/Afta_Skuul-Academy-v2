from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Q
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from .models import Assignment, Submission
from accounts.models import User
from batches.models import Batch


# ============================================================================
# CUSTOM FILTERS
# ============================================================================

class SubjectFilter(SimpleListFilter):
    """Filter assignments by batch subject."""
    title = _('Subject')
    parameter_name = 'subject'

    def lookups(self, request, model_admin):
        queryset = model_admin.get_queryset(request)
        subjects = set(queryset.values_list('batch__subject', flat=True).distinct())
        return [(s, s) for s in sorted(subjects)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(batch__subject=self.value())
        return queryset


class GradeLevelFilter(SimpleListFilter):
    """Filter assignments by batch grade level."""
    title = _('Grade Level')
    parameter_name = 'grade_level'

    def lookups(self, request, model_admin):
        queryset = model_admin.get_queryset(request)
        grades = set(queryset.values_list('batch__grade_level', flat=True).distinct())
        return [(g, g) for g in sorted(grades)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(batch__grade_level=self.value())
        return queryset


class AssignmentTypeFilter(SimpleListFilter):
    """Filter submissions by assignment type."""
    title = _('Assignment Type')
    parameter_name = 'assignment_type'

    def lookups(self, request, model_admin):
        return (
            ('exercise', _('Exercise')),
            ('exam', _('Exam')),
        )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(assignment__type=self.value())
        return queryset


class SubmissionSubjectFilter(SimpleListFilter):
    """Filter submissions by batch subject."""
    title = _('Subject')
    parameter_name = 'subject'

    def lookups(self, request, model_admin):
        queryset = model_admin.get_queryset(request)
        # FIX: Use '__' for nested relationships
        subjects = set(queryset.values_list('assignment__batch__subject', flat=True).distinct())
        return [(s, s) for s in sorted(subjects)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(assignment__batch__subject=self.value())
        return queryset


class SubmissionStatusFilter(SimpleListFilter):
    """Filter submissions by grading status."""
    title = _('Grading Status')
    parameter_name = 'grading_status'

    def lookups(self, request, model_admin):
        return (
            ('graded', _('Graded')),
            ('ungraded', _('Ungraded')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'graded':
            return queryset.filter(marks_obtained__isnull=False)
        elif self.value() == 'ungraded':
            return queryset.filter(marks_obtained__isnull=True)
        return queryset


# ============================================================================
# INLINES
# ============================================================================

class SubmissionInline(admin.TabularInline):
    """Inline display of submissions within an assignment."""
    model = Submission
    extra = 0
    fields = ('student_link', 'submitted_at', 'marks_obtained', 'is_auto_graded', 'file_upload')
    readonly_fields = ('student_link', 'submitted_at')
    can_delete = False
    show_change_link = True
    verbose_name = _('Submission')
    verbose_name_plural = _('Submissions')

    def student_link(self, obj):
        url = reverse('admin:accounts_user_change', args=[obj.student.id])
        return format_html('<a href="{}">{}</a>', url, obj.student.get_full_name())
    student_link.short_description = _('Student')


# ============================================================================
# ASSIGNMENT ADMIN
# ============================================================================

@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Assignment model with role‑based access.
    """
    # List view
    list_display = (
        'title', 'batch_link', 'type', 'total_marks',
        'due_date_display', 'is_overdue_display', 'submission_count'
    )
    list_filter = (
        'type',
        SubjectFilter,
        GradeLevelFilter,
        'due_date',
        'batch__teacher',
    )
    search_fields = ('title', 'description', 'batch__name')
    list_select_related = ('batch', 'batch__teacher')
    ordering = ('-due_date',)
    readonly_fields = ('created_at', 'updated_at')

    # Form layout
    fieldsets = (
        (None, {
            'fields': ('batch', 'lesson', 'title', 'description', 'type', 'total_marks')
        }),
        (_('Timing'), {
            'fields': ('due_date', 'time_limit_minutes'),
        }),
        (_('Questions'), {
            'fields': ('questions',),
            'classes': ('collapse',),
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    inlines = [SubmissionInline]
    actions = ['mark_as_overdue', 'duplicate_assignment']

    # ---------- Queryset filtering ----------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role == 'admin':
            return qs
        elif request.user.role == 'teacher':
            return qs.filter(batch__teacher=request.user)
        return qs.none()

    # ---------- List display methods ----------
    def batch_link(self, obj):
        url = reverse('admin:batches_batch_change', args=[obj.batch.id])
        return format_html('<a href="{}">{}</a>', url, obj.batch.name)
    batch_link.short_description = _('Batch')
    batch_link.admin_order_field = 'batch__name'

    def due_date_display(self, obj):
        # Use mark_safe with f-string
        return mark_safe(f'<span class="nowrap">{obj.due_date.strftime("%d %b %Y, %H:%M")}</span>')
    due_date_display.short_description = _('Due Date')
    due_date_display.admin_order_field = 'due_date'

    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return mark_safe('<span class="badge bg-danger">🔴 Overdue</span>')
        return mark_safe('<span class="badge bg-success">✅ Active</span>')
    is_overdue_display.short_description = _('Status')
    is_overdue_display.admin_order_field = 'due_date'

    def submission_count(self, obj):
        count = obj.submissions.count()
        graded = obj.submissions.filter(marks_obtained__isnull=False).count()
        if count == 0:
            return mark_safe('<span class="text-muted">0</span>')
        return mark_safe(f'<span class="badge bg-secondary">{graded}/{count} graded</span>')
    submission_count.short_description = _('Submissions')

    # ---------- Actions ----------
    def mark_as_overdue(self, request, queryset):
        count = queryset.count()
        self.message_user(
            request,
            f'📌 {count} assignment(s) would be marked as overdue. '
            '(This is a simulation – overdue status is calculated automatically.)'
        )
    mark_as_overdue.short_description = _('Simulate overdue status')

    def duplicate_assignment(self, request, queryset):
        count = 0
        for assignment in queryset:
            assignment.pk = None
            assignment.title = f"{assignment.title} (Copy)"
            assignment.created_at = None
            assignment.updated_at = None
            assignment.save()
            count += 1
        self.message_user(request, f'✅ {count} assignment(s) duplicated.')
    duplicate_assignment.short_description = _('Duplicate selected assignments')

    # ---------- Field restrictions ----------
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "batch" and request.user.role == 'teacher':
            kwargs["queryset"] = Batch.objects.filter(teacher=request.user, is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ============================================================================
# SUBMISSION ADMIN
# ============================================================================

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Submission model with role‑based access.
    """
    # List view
    list_display = (
        'student_link', 'assignment_link', 'submitted_at_display',
        'marks_obtained_display', 'grade_percentage_display',
        'is_graded_display', 'is_auto_graded', 'is_late_display'
    )
    list_filter = (
        'is_auto_graded',
        AssignmentTypeFilter,
        SubmissionSubjectFilter,
        SubmissionStatusFilter,
        'submitted_at',
    )
    search_fields = ('student_first_name', 'studentlast_name', 'assignment_title')
    list_select_related = ('student', 'assignment', 'assignment__batch')
    date_hierarchy = 'submitted_at'
    ordering = ('-submitted_at',)
    readonly_fields = ('submitted_at',)

    fieldsets = (
        (None, {
            'fields': ('student', 'assignment', 'file_upload', 'answers')
        }),
        (_('Grading'), {
            'fields': ('marks_obtained', 'feedback', 'graded_by', 'graded_at', 'is_auto_graded'),
        }),
    )

    actions = ['auto_grade_selected', 'clear_grades']

    # ---------- Queryset filtering ----------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role == 'admin':
            return qs
        elif request.user.role == 'teacher':
            return qs.filter(assignment_batch_teacher=request.user)
        return qs.none()

    # ---------- List display methods ----------
    def student_link(self, obj):
        url = reverse('admin:accounts_user_change', args=[obj.student.id])
        return format_html('<a href="{}">{}</a>', url, obj.student.get_full_name())
    student_link.short_description = _('Student')
    student_link.admin_order_field = 'student__first_name'

    def assignment_link(self, obj):
        url = reverse('admin:assignments_assignment_change', args=[obj.assignment.id])
        return format_html('<a href="{}">{}</a>', url, obj.assignment.title)
    assignment_link.short_description = _('Assignment')
    assignment_link.admin_order_field = 'assignment__title'

    def submitted_at_display(self, obj):
        return mark_safe(f'<span class="nowrap">{obj.submitted_at.strftime("%d %b %Y, %H:%M")}</span>')
    submitted_at_display.short_description = _('Submitted At')
    submitted_at_display.admin_order_field = 'submitted_at'

    def marks_obtained_display(self, obj):
        if obj.marks_obtained is not None:
            return mark_safe(f'<span class="fw-bold">{obj.marks_obtained}/{obj.assignment.total_marks}</span>')
        return mark_safe('<span class="text-muted">—</span>')
    marks_obtained_display.short_description = _('Marks')
    marks_obtained_display.admin_order_field = 'marks_obtained'

    def grade_percentage_display(self, obj):
        if obj.marks_obtained is not None and obj.assignment.total_marks > 0:
            # Convert to float for formatting
            percentage = float((obj.marks_obtained / obj.assignment.total_marks) * 100)
            color = 'success' if percentage >= 80 else 'warning' if percentage >= 50 else 'danger'
            return mark_safe(f'<span class="badge bg-{color}">{percentage:.0f}%</span>')
        return mark_safe('<span class="text-muted">—</span>')
    grade_percentage_display.short_description = _('Score')

    def is_graded_display(self, obj):
        if obj.marks_obtained is not None:
            return mark_safe('<span class="badge bg-success">✅ Graded</span>')
        return mark_safe('<span class="badge bg-warning text-dark">⏳ Pending</span>')
    is_graded_display.short_description = _('Grading Status')

    def is_late_display(self, obj):
        if obj.is_late:
            return mark_safe('<span class="badge bg-danger">⚠️ Late</span>')
        return mark_safe('<span class="badge bg-secondary">On Time</span>')
    is_late_display.short_description = _('Timing')

    # ---------- Actions ----------
    def auto_grade_selected(self, request, queryset):
        count = 0
        for submission in queryset:
            if submission.marks_obtained is None:
                all_mcq = all(q.get('type') == 'mcq' for q in submission.assignment.questions)
                if all_mcq:
                    submission.auto_grade_mcq()
                    count += 1
        self.message_user(request, f'✅ Auto-graded {count} submission(s).')
    auto_grade_selected.short_description = _('Auto-grade selected (MCQ only)')

    def clear_grades(self, request, queryset):
        count = queryset.update(
            marks_obtained=None,
            feedback='',
            graded_by=None,
            graded_at=None,
            is_auto_graded=False
        )
        self.message_user(request, f'⏹️ Cleared grades for {count} submission(s).')
    clear_grades.short_description = _('Clear grades for selected submissions')

    # ---------- Field restrictions ----------
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.marks_obtained is not None:
            return self.readonly_fields + ('student', 'assignment', 'file_upload', 'answers')
        return self.readonly_fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "assignment" and request.user.role == 'teacher':
            kwargs["queryset"] = Assignment.objects.filter(batch__teacher=request.user)
        elif db_field.name == "student" and request.user.role == 'teacher':
            kwargs["queryset"] = User.objects.filter(
                role='student',
                enrollment_batch_teacher=request.user,
                enrollment__is_active=True
            ).distinct()
        elif db_field.name == "graded_by" and request.user.role == 'teacher':
            kwargs["queryset"] = User.objects.filter(id=request.user.id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)