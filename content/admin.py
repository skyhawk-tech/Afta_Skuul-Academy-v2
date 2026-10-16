from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Q
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from .models import Lesson, LessonProgress, LessonQuestion, LessonReply
from .models import Lesson, LessonProgress
from batches.models import Batch
from accounts.models import User


# ============================================================================
# CUSTOM FILTERS
# ============================================================================

class LessonSubjectFilter(SimpleListFilter):
    """Filter lessons by the subject of their associated batch."""
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


class LessonGradeFilter(SimpleListFilter):
    """Filter lessons by the grade level of their associated batch."""
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


class LessonReleaseStatusFilter(SimpleListFilter):
    """Filter lessons by their release status."""
    title = _('Release Status')
    parameter_name = 'release_status'

    def lookups(self, request, model_admin):
        from django.utils import timezone
        return (
            ('released', _('Released')),
            ('draft', _('Draft')),
        )

    def queryset(self, request, queryset):
        from django.utils import timezone
        if self.value() == 'released':
            return queryset.filter(Q(release_date_lte=timezone.now()) | Q(release_date_isnull=True))
        elif self.value() == 'draft':
            return queryset.filter(release_date__gt=timezone.now())
        return queryset


class ProgressStudentFilter(SimpleListFilter):
    """Filter progress records by student name."""
    title = _('Student')
    parameter_name = 'student'

    def lookups(self, request, model_admin):
        if request.user.role == 'teacher':
            students = User.objects.filter(
                role='student',
                enrollment_batch_teacher=request.user,
                enrollment__is_active=True
            ).distinct()
        else:
            students = User.objects.filter(role='student')
        return [(s.id, s.get_full_name()) for s in students]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(student_id=self.value())
        return queryset


class ProgressLessonFilter(SimpleListFilter):
    """Filter progress records by lesson title."""
    title = _('Lesson')
    parameter_name = 'lesson'

    def lookups(self, request, model_admin):
        if request.user.role == 'teacher':
            lessons = Lesson.objects.filter(batch__teacher=request.user)
        else:
            lessons = Lesson.objects.all()
        return [(l.id, l.title) for l in lessons]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(lesson_id=self.value())
        return queryset


class ProgressCompletionFilter(SimpleListFilter):
    """Filter progress records by completion status."""
    title = _('Completion Status')
    parameter_name = 'completion'

    def lookups(self, request, model_admin):
        return (
            ('completed', _('Completed')),
            ('incomplete', _('Incomplete')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'completed':
            return queryset.filter(is_completed=True)
        elif self.value() == 'incomplete':
            return queryset.filter(is_completed=False)
        return queryset


# ============================================================================
# INLINES
# ============================================================================

class LessonProgressInline(admin.TabularInline):
    """Inline display of student progress within a lesson."""
    model = LessonProgress
    extra = 0
    fields = ('student', 'total_watch_seconds', 'watch_percentage', 'is_completed', 'last_activity')
    readonly_fields = ('student', 'total_watch_seconds', 'watch_percentage', 'is_completed', 'last_activity')
    can_delete = False
    show_change_link = True
    verbose_name = _('Student Progress')
    verbose_name_plural = _('Student Progress')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role == 'teacher':
            return qs.filter(lesson_batch_teacher=request.user)
        return qs


# ============================================================================
# LESSON ADMIN
# ============================================================================

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Lesson model with role‑based access control.
    """
    # List view configuration
    list_display = (
        'title', 'batch_link', 'subject_display', 'grade_display',
        'video_duration_formatted', 'progress_summary',
        'required_watch_percentage', 'release_status_display',
        'order', 'created_at'
    )
    list_filter = (
        LessonSubjectFilter,
        LessonGradeFilter,
        LessonReleaseStatusFilter,
        'batch__teacher',
        'required_watch_percentage',
        'created_at',
    )
    search_fields = ('title', 'description', 'batch__name')
    ordering = ('batch', 'order', '-created_at')
    readonly_fields = ('created_at', 'updated_at')

    # Form layout
    fieldsets = (
        (None, {
            'fields': ('batch', 'title', 'description')
        }),
        (_('Media'), {
            'fields': ('video_file', 'video_url', 'video_duration', 'notes_file'),
            'classes': ('wide',),
        }),
        (_('Settings'), {
            'fields': ('order', 'required_watch_percentage', 'release_date'),
            'classes': ('wide',),
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    inlines = [LessonProgressInline]
    actions = ['reset_progress_for_selected_lessons']

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

    def subject_display(self, obj):
        return obj.batch.subject
    subject_display.short_description = _('Subject')
    subject_display.admin_order_field = 'batch__subject'

    def grade_display(self, obj):
        return obj.batch.grade_level
    grade_display.short_description = _('Grade')
    grade_display.admin_order_field = 'batch__grade_level'

    def video_duration_formatted(self, obj):
        return obj.duration_formatted
    video_duration_formatted.short_description = _('Duration')
    video_duration_formatted.admin_order_field = 'video_duration'

    def progress_summary(self, obj):
        """Display a summary of student progress for this lesson."""
        total = obj.progress.count()
        completed = obj.progress.filter(is_completed=True).count()
        if total == 0:
            return mark_safe('<span class="text-muted">No data</span>')
        percentage = (completed / total) * 100
        color = 'success' if percentage >= 80 else 'warning' if percentage >= 50 else 'danger'
        return mark_safe(
            f'<span class="badge bg-{color}">{completed}/{total} ({percentage:.1f}%)</span>'
        )
    progress_summary.short_description = _('Progress')

    def release_status_display(self, obj):
        if obj.is_released:
            return mark_safe('<span class="badge bg-success">Released</span>')
        return mark_safe('<span class="badge bg-secondary">Draft</span>')
    release_status_display.short_description = _('Status')
    release_status_display.admin_order_field = 'release_date'

    # ---------- Actions ----------
    def reset_progress_for_selected_lessons(self, request, queryset):
        """Delete all progress records for selected lessons."""
        total_deleted = 0
        lessons = queryset.prefetch_related('progress')
        for lesson in lessons:
            count, _ = lesson.progress.all().delete()
            total_deleted += count
        self.message_user(
            request,
            f'Deleted {total_deleted} progress record(s) for {queryset.count()} lesson(s).'
        )
    reset_progress_for_selected_lessons.short_description = _('Reset progress for selected lessons')

    # ---------- Foreign key restrictions ----------
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "batch" and request.user.role == 'teacher':
            kwargs["queryset"] = Batch.objects.filter(teacher=request.user, is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ============================================================================
# LESSON PROGRESS ADMIN
# ============================================================================

@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    """
    Admin configuration for the LessonProgress model.
    """
    list_display = (
        'student_link', 'lesson_link', 'batch_link', 'total_watch_seconds',
        'watch_percentage_display', 'completion_status_display', 'last_activity_display'
    )
    list_filter = (
        ProgressCompletionFilter,
        ProgressStudentFilter,
        ProgressLessonFilter,
        'last_activity',
    )
    search_fields = ('student_first_name', 'studentlast_name', 'lesson_title')
    ordering = ('-last_activity', '-watch_percentage')
    readonly_fields = ('first_watch', 'last_activity', 'total_watch_seconds', 'watch_percentage')
    date_hierarchy = 'last_activity'

    fieldsets = (
        (None, {
            'fields': ('student', 'lesson')
        }),
        (_('Progress'), {
            'fields': ('total_watch_seconds', 'watch_percentage', 'is_completed')
        }),
        (_('Timestamps'), {
            'fields': ('first_watch', 'last_activity'),
            'classes': ('collapse',)
        }),
    )

    actions = ['mark_as_completed', 'mark_as_incomplete']

    # ---------- Queryset filtering ----------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role == 'admin':
            return qs
        elif request.user.role == 'teacher':
            return qs.filter(lesson_batch_teacher=request.user)
        return qs.none()

    # ---------- List display methods ----------
    def student_link(self, obj):
        url = reverse('admin:accounts_user_change', args=[obj.student.id])
        return format_html('<a href="{}">{}</a>', url, obj.student.get_full_name())
    student_link.short_description = _('Student')
    student_link.admin_order_field = 'student__first_name'

    def lesson_link(self, obj):
        url = reverse('admin:content_lesson_change', args=[obj.lesson.id])
        return format_html('<a href="{}">{}</a>', url, obj.lesson.title)
    lesson_link.short_description = _('Lesson')
    lesson_link.admin_order_field = 'lesson__title'

    def batch_link(self, obj):
        url = reverse('admin:batches_batch_change', args=[obj.lesson.batch.id])
        return format_html('<a href="{}">{}</a>', url, obj.lesson.batch.name)
    batch_link.short_description = _('Batch')
    batch_link.admin_order_field = 'lesson_batch_name'

    def watch_percentage_display(self, obj):
        percentage = obj.watch_percentage
        color = 'success' if obj.is_completed else 'warning'
        # Use mark_safe with f-string, convert to float for formatting
        return mark_safe(
            f'<div class="progress" style="width: 80px; height: 16px; display: inline-block;">'
            f'<div class="progress-bar bg-{color}" style="width: {percentage:.0f}%;">{percentage:.0f}%</div>'
            f'</div>'
        )
    watch_percentage_display.short_description = _('Watched')
    watch_percentage_display.admin_order_field = 'watch_percentage'

    def completion_status_display(self, obj):
        if obj.is_completed:
            return mark_safe('<span class="badge bg-success">✅ Completed</span>')
        return mark_safe('<span class="badge bg-warning text-dark">⏳ In Progress</span>')
    completion_status_display.short_description = _('Status')
    completion_status_display.admin_order_field = 'is_completed'

    def last_activity_display(self, obj):
        return obj.last_activity.strftime('%d %b %Y, %H:%M')
    last_activity_display.short_description = _('Last Activity')
    last_activity_display.admin_order_field = 'last_activity'

    # ---------- Actions ----------
    def mark_as_completed(self, request, queryset):
        count = queryset.update(is_completed=True)
        self.message_user(request, f'✅ {count} progress record(s) marked as completed.')
    mark_as_completed.short_description = _('Mark selected as completed')

    def mark_as_incomplete(self, request, queryset):
        count = queryset.update(is_completed=False)
        self.message_user(request, f'⏳ {count} progress record(s) marked as incomplete.')
    mark_as_incomplete.short_description = _('Mark selected as incomplete')

    # ---------- Foreign key restrictions ----------
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "lesson" and request.user.role == 'teacher':
            kwargs["queryset"] = Lesson.objects.filter(batch__teacher=request.user)
        elif db_field.name == "student" and request.user.role == 'teacher':
            kwargs["queryset"] = User.objects.filter(
                role='student',
                enrollment_batch_teacher=request.user,
                enrollment__is_active=True
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
@admin.register(LessonQuestion)
class LessonQuestionAdmin(admin.ModelAdmin):
    list_display = ('student', 'lesson', 'body_short', 'reply_count', 'is_resolved', 'created_at')
    list_filter = ('is_resolved', 'lesson__batch', 'created_at')
    search_fields = ('body', 'student_username', 'lesson_title')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'

    def body_short(self, obj):
        return obj.body[:60] + ('…' if len(obj.body) > 60 else '')
    body_short.short_description = 'Question'


@admin.register(LessonReply)
class LessonReplyAdmin(admin.ModelAdmin):
    list_display = ('author', 'question_short', 'created_at')
    list_filter = ('author__role', 'created_at')
    search_fields = ('body', 'author__username')
    readonly_fields = ('created_at', 'updated_at')

    def question_short(self, obj):
        return obj.question.body[:50] + ('…' if len(obj.question.body) > 50 else '')
    question_short.short_description = 'Reply to'