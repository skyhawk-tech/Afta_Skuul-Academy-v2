from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Q
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.urls import reverse

from .models import Batch, Enrollment
from accounts.models import User


# ============================================================================
# CUSTOM FILTERS
# ============================================================================

class BatchSubjectFilter(SimpleListFilter):
    """Filter batches by their subject."""
    title = _('Subject')
    parameter_name = 'subject'

    def lookups(self, request, model_admin):
        queryset = model_admin.get_queryset(request)
        subjects = set(queryset.values_list('subject', flat=True).distinct())
        return [(s, s) for s in sorted(subjects)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(subject=self.value())
        return queryset


class BatchGradeFilter(SimpleListFilter):
    """Filter batches by grade level."""
    title = _('Grade Level')
    parameter_name = 'grade_level'

    def lookups(self, request, model_admin):
        queryset = model_admin.get_queryset(request)
        grades = set(queryset.values_list('grade_level', flat=True).distinct())
        return [(g, g) for g in sorted(grades)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(grade_level=self.value())
        return queryset


class EnrollmentBatchFilter(SimpleListFilter):
    """Filter enrollments by batch name, restricted to the teacher's own batches."""
    title = _('Batch')
    parameter_name = 'batch'

    def lookups(self, request, model_admin):
        if request.user.role == 'admin':
            batches = Batch.objects.filter(is_active=True)
        else:
            batches = Batch.objects.filter(teacher=request.user, is_active=True)
        return [(b.id, b.name) for b in batches.order_by('name')]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(batch_id=self.value())
        return queryset


# ============================================================================
# INLINES
# ============================================================================

class EnrollmentInline(admin.TabularInline):
    """Inline display of student enrollments within a batch."""
    model = Enrollment
    extra = 0
    fields = ('student', 'is_active', 'enrolled_on')
    readonly_fields = ('enrolled_on',)
    show_change_link = True
    can_delete = False
    verbose_name = _('Enrollment')
    verbose_name_plural = _('Enrollments')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Teacher sees only enrollments for batches they own (enforced by parent admin)
        return qs


# ============================================================================
# BATCH ADMIN
# ============================================================================

@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Batch model with role‑based access.
    """
    # List view
    list_display = (
        'name', 'subject', 'grade_level', 'teacher_link', 'student_count',
        'fee_per_session', 'is_active', 'created_at'
    )
    list_filter = (
        'is_active',
        BatchSubjectFilter,
        BatchGradeFilter,
        'teacher',
        'created_at',
    )
    search_fields = ('name', 'subject', 'teacher_first_name', 'teacher_last_name')
    list_select_related = ('teacher',)
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    # Form layout
    fieldsets = (
        (None, {
            'fields': ('name', 'subject', 'grade_level', 'teacher', 'schedule')
        }),
        (_('Capacity & Fees'), {
            'fields': ('max_capacity', 'fee_per_session'),
        }),
        (_('Status'), {
            'fields': ('is_active',),
        }),
        (_('Metadata'), {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )

    inlines = [EnrollmentInline]
    actions = ['activate_batches', 'deactivate_batches']

    # ---------- Queryset filtering ----------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role == 'admin':
            return qs
        elif request.user.role == 'teacher':
            return qs.filter(teacher=request.user)
        return qs.none()

    # ---------- List display methods ----------
    def teacher_link(self, obj):
        url = reverse('admin:accounts_user_change', args=[obj.teacher.id])
        return format_html('<a href="{}">{}</a>', url, obj.teacher.get_full_name())
    teacher_link.short_description = _('Teacher')
    teacher_link.admin_order_field = 'teacher__first_name'

    def student_count(self, obj):
        return obj.enrollments.filter(is_active=True).count()
    student_count.short_description = _('Students')
    student_count.admin_order_field = 'enrollments_count'

    # ---------- Actions ----------
    def activate_batches(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'✅ {count} batch(es) activated.')
    activate_batches.short_description = _('Activate selected batches')

    def deactivate_batches(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'⏹️ {count} batch(es) deactivated.')
    deactivate_batches.short_description = _('Deactivate selected batches')

    # ---------- Field restrictions ----------
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "teacher":
            if request.user.role == 'teacher':
                kwargs["queryset"] = User.objects.filter(id=request.user.id)
            elif request.user.role == 'admin':
                kwargs["queryset"] = User.objects.filter(role='teacher', is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        # Teachers cannot change the teacher field after creation
        if request.user.role == 'teacher' and obj:
            return self.readonly_fields + ('teacher',)
        return self.readonly_fields


# ============================================================================
# ENROLLMENT ADMIN
# ============================================================================

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Enrollment model with role‑based access.
    """
    list_display = (
        'student_link', 'batch_link', 'teacher_link', 'is_active', 'enrolled_on'
    )
    list_filter = (
        'is_active',
        EnrollmentBatchFilter,
        'enrolled_on',
    )
    search_fields = ('student_first_name', 'studentlast_name', 'batch_name')
    list_select_related = ('student', 'batch', 'batch__teacher')
    date_hierarchy = 'enrolled_on'
    ordering = ('-enrolled_on',)
    readonly_fields = ('enrolled_on',)

    fieldsets = (
        (None, {
            'fields': ('student', 'batch', 'is_active')
        }),
        (_('Metadata'), {
            'fields': ('enrolled_on',),
            'classes': ('collapse',),
        }),
    )

    actions = ['activate_enrollments', 'deactivate_enrollments']

    # ---------- Queryset filtering ----------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role == 'admin':
            return qs
        elif request.user.role == 'teacher':
            return qs.filter(batch__teacher=request.user)
        return qs.none()

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

    def teacher_link(self, obj):
        return obj.batch.teacher.get_full_name()
    teacher_link.short_description = _('Teacher')
    teacher_link.admin_order_field = 'batch_teacher_first_name'

    # ---------- Actions ----------
    def activate_enrollments(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'✅ {count} enrollment(s) activated.')
    activate_enrollments.short_description = _('Activate selected enrollments')

    def deactivate_enrollments(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'⏹️ {count} enrollment(s) deactivated.')
    deactivate_enrollments.short_description = _('Deactivate selected enrollments')

    # ---------- Field restrictions ----------
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "batch" and request.user.role == 'teacher':
            kwargs["queryset"] = Batch.objects.filter(teacher=request.user, is_active=True)
        elif db_field.name == "student" and request.user.role == 'teacher':
            # Teachers can only see students (but not restrict by batch)
            kwargs["queryset"] = User.objects.filter(role='student', is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
    
