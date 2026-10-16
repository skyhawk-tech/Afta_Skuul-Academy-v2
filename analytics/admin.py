from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Q
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from .models import DailyAttendanceSnapshot, StudentProgressSnapshot
from accounts.models import User
from batches.models import Batch


# ============================================================================
# CUSTOM FILTERS
# ============================================================================

class BatchTeacherFilter(SimpleListFilter):
    """Filter snapshots by the teacher of the associated batch."""
    title = _('Teacher')
    parameter_name = 'teacher'

    def lookups(self, request, model_admin):
        teachers = User.objects.filter(
            role='teacher',
            batches__is_active=True
        ).distinct().order_by('first_name', 'last_name')
        return [(t.id, t.get_full_name()) for t in teachers]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(batch__teacher_id=self.value())
        return queryset


class BatchSubjectFilter(SimpleListFilter):
    """Filter snapshots by batch subject."""
    title = _('Subject')
    parameter_name = 'subject'

    def lookups(self, request, model_admin):
        subjects = (
            Batch.objects.filter(is_active=True)
            .values_list('subject', flat=True)
            .distinct()
            .order_by('subject')
        )
        return [(s, s) for s in subjects]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(batch__subject=self.value())
        return queryset


class AttendanceDateRangeFilter(SimpleListFilter):
    """Filter snapshots by a date range."""
    title = _('Date Range')
    parameter_name = 'date_range'

    def lookups(self, request, model_admin):
        return (
            ('today', _('Today')),
            ('week', _('Last 7 days')),
            ('month', _('Last 30 days')),
        )

    def queryset(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta

        if self.value() == 'today':
            return queryset.filter(date=timezone.now().date())
        elif self.value() == 'week':
            return queryset.filter(date__gte=timezone.now().date() - timedelta(days=7))
        elif self.value() == 'month':
            return queryset.filter(date__gte=timezone.now().date() - timedelta(days=30))
        return queryset


# ============================================================================
# DAILY ATTENDANCE SNAPSHOT ADMIN
# ============================================================================

@admin.register(DailyAttendanceSnapshot)
class DailyAttendanceSnapshotAdmin(admin.ModelAdmin):
    """
    Admin configuration for DailyAttendanceSnapshot.
    Provides an overview of daily attendance per batch.
    """
    list_display = (
        'batch_link', 'date_display', 'total_enrolled',
        'attended_count', 'attendance_percentage_display'
    )
    list_filter = (
        BatchTeacherFilter,
        BatchSubjectFilter,
        AttendanceDateRangeFilter,
        'date',
    )
    search_fields = ('batch__name',)
    list_select_related = ('batch', 'batch__teacher')
    date_hierarchy = 'date'
    ordering = ('-date', '-batch__name')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('batch', 'date', 'total_enrolled', 'attended_count')
        }),
        (_('Calculated Fields'), {
            'fields': ('attendance_percentage', 'average_watch_percentage'),
            'classes': ('collapse',),
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # ---------- List display methods ----------
    def batch_link(self, obj):
        url = reverse('admin:batches_batch_change', args=[obj.batch.id])
        return format_html('<a href="{}">{}</a>', url, obj.batch.name)
    batch_link.short_description = _('Batch')
    batch_link.admin_order_field = 'batch__name'

    def date_display(self, obj):
        return obj.date.strftime('%d %b %Y')
    date_display.short_description = _('Date')
    date_display.admin_order_field = 'date'

    def attendance_percentage_display(self, obj):
        # ✅ FIX: Convert to float and use mark_safe with f-string
        percentage = float(obj.attendance_percentage or 0)
        if percentage >= 80:
            color = 'success'
        elif percentage >= 50:
            color = 'warning'
        else:
            color = 'danger'
        return mark_safe(
            f'<span class="badge bg-{color}">{percentage:.1f}%</span>'
        )
    attendance_percentage_display.short_description = _('Attendance Rate')
    attendance_percentage_display.admin_order_field = 'attendance_percentage'


# ============================================================================
# STUDENT PROGRESS SNAPSHOT ADMIN
# ============================================================================

@admin.register(StudentProgressSnapshot)
class StudentProgressSnapshotAdmin(admin.ModelAdmin):
    """
    Admin configuration for StudentProgressSnapshot.
    Tracks cumulative progress per student per batch.
    """
    list_display = (
        'student_link', 'batch_link', 'snapshot_date_display',
        'completion_percentage_display', 'average_grade_display'
    )
    list_filter = (
        BatchTeacherFilter,
        BatchSubjectFilter,
        'snapshot_date',
    )
    search_fields = ('student_first_name', 'studentlast_name', 'batch_name')
    list_select_related = ('student', 'batch', 'batch__teacher')
    date_hierarchy = 'snapshot_date'
    ordering = ('-snapshot_date',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('student', 'batch', 'snapshot_date')
        }),
        (_('Progress'), {
            'fields': ('total_lessons', 'total_lessons_completed', 'completion_percentage')
        }),
        (_('Grades'), {
            'fields': ('average_grade',),
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # ---------- List display methods ----------
    def student_link(self, obj):
        url = reverse('admin:accounts_user_change', args=[obj.student.id])
        return format_html('<a href="{}">{}</a>', url, obj.student.get_full_name())
    student_link.short_description = _('Student')
    student_link.admin_order_field = 'student__first_name'

    def batch_link(self, obj):
        url = reverse('admin:batches_batch_change', args=[obj.batch.id])
        return format_html('<a href="{}">{}</a>', url, obj.batch.name)
    batch_link.short_description = _('Batch')
    batch_link.admin_order_field = 'batch__name'

    def snapshot_date_display(self, obj):
        return obj.snapshot_date.strftime('%d %b %Y')
    snapshot_date_display.short_description = _('Snapshot Date')
    snapshot_date_display.admin_order_field = 'snapshot_date'

    def completion_percentage_display(self, obj):
        # ✅ FIX: Convert to float and use mark_safe with f-string
        percentage = float(obj.completion_percentage or 0)
        if percentage >= 80:
            color = 'success'
        elif percentage >= 50:
            color = 'warning'
        else:
            color = 'danger'
        return mark_safe(
            f'<span class="badge bg-{color}">{percentage:.1f}%</span>'
        )
    completion_percentage_display.short_description = _('Completion')
    completion_percentage_display.admin_order_field = 'completion_percentage'

    def average_grade_display(self, obj):
        # ✅ FIX: Convert to float and use mark_safe with f-string
        grade = float(obj.average_grade or 0)
        if grade == 0:
            return mark_safe('<span class="text-muted">—</span>')
        if grade >= 70:
            color = 'success'
        elif grade >= 50:
            color = 'warning'
        else:
            color = 'danger'
        return mark_safe(
            f'<span class="badge bg-{color}">{grade:.1f}</span>'
        )
    average_grade_display.short_description = _('Avg Grade')
    average_grade_display.admin_order_field = 'average_grade'