from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.contrib.admin import SimpleListFilter
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.contrib.admin.models import LogEntry

from .models import User


# ============================================================================
# CUSTOM FILTERS
# ============================================================================

class TSCFilter(SimpleListFilter):
    """Filter users by TSC status (relevant only for teachers)."""
    title = _('TSC Status')
    parameter_name = 'tsc_status'

    def lookups(self, request, model_admin):
        return (
            ('with', _('With TSC')),
            ('without', _('Without TSC (teachers)')),
        )

    def queryset(self, request, queryset):
        if self.value() == 'with':
            return queryset.exclude(tsc_number__isnull=True).exclude(tsc_number='')
        if self.value() == 'without':
            return queryset.filter(role='teacher').filter(
                tsc_number__isnull=True
            ) | queryset.filter(role='teacher', tsc_number='')
        return queryset


# ============================================================================
# USER ADMIN
# ============================================================================

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin for the User model.
    Extends Django's built-in UserAdmin to include custom fields (role, TSC, children)
    and role-based access.
    """

    # ---------- List view ----------
    list_display = (
        'username', 'full_name', 'email', 'role_badge',
        'tsc_number_display',            # ← TSC column
        'phone', 'children_count',
        'is_active_badge', 'date_joined_display',
    )
    list_filter = (
        'role', 'is_active', 'is_staff', 'is_superuser',
        'date_joined', 'groups',
        TSCFilter,                       # ← TSC filter
    )
    search_fields = (
        'username', 'email', 'first_name', 'last_name', 'phone',
        'tsc_number',                    # ← searchable
    )
    ordering = ('-date_joined',)
    date_hierarchy = 'date_joined'

    # ---------- Detail form ----------
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal Information'), {
            'fields': ('first_name', 'last_name', 'email', 'phone')
        }),
        (_('Teacher Information'), {
            'fields': ('subjects', 'tsc_number'),   # ← TSC here
            'description': _(
                'Only relevant for teachers. TSC number must be 6–8 digits and unique.'
            ),
        }),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser',
                       'groups', 'user_permissions'),
        }),
        (_('Important Dates'), {'fields': ('last_login', 'date_joined')}),
        (_('Tuition Specific'), {
            'fields': ('role', 'children'),
            'classes': ('collapse',),
            'description': _(
                'Role determines dashboard access. '
                'For parents, link to student accounts via "children".'
            ),
        }),
    )

    # ---------- Add form ----------
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'first_name', 'last_name',
                'phone', 'role', 'subjects', 'tsc_number',   # ← added
                'password1', 'password2',
            ),
        }),
    )

    filter_horizontal = ('groups', 'user_permissions', 'children')

    # ---------- Actions ----------
    actions = [
        'activate_users',
        'deactivate_users',
        'set_role_to_teacher',
        'set_role_to_student',
        'set_role_to_parent',
    ]

    # ========================================================================
    # LOGGING OVERRIDES – prevent FK errors on django_admin_log
    # ========================================================================
    def log_addition(self, request, object, message):
        pass

    def log_change(self, request, object, message):
        pass

    def log_deletion(self, request, object, object_repr):
        pass

    # ---------- Queryset filtering ----------
    def get_queryset(self, request):
        """Restrict admin visibility based on user role."""
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.role == 'admin':
            return qs
        return qs.filter(id=request.user.id)

    # ---------- List display methods ----------
    def full_name(self, obj):
        return obj.get_full_name() or obj.username
    full_name.short_description = _('Full Name')
    full_name.admin_order_field = 'first_name'

    def role_badge(self, obj):
        colors = {
            'admin': 'danger',
            'teacher': 'primary',
            'student': 'success',
            'parent': 'info',
        }
        color = colors.get(obj.role, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color,
            obj.get_role_display()
        )
    role_badge.short_description = _('Role')
    role_badge.admin_order_field = 'role'

    def tsc_number_display(self, obj):
        """Show TSC number for teachers, dash for others."""
        if obj.role != 'teacher':
            return mark_safe('<span class="text-muted">—</span>')
        if not obj.tsc_number:
            return mark_safe(
                '<span class="badge bg-warning text-dark">Missing</span>'
            )
        return format_html(
            '<span class="badge bg-light text-dark border">'
            '<i class="fas fa-id-card me-1"></i>{}</span>',
            obj.tsc_number
        )
    tsc_number_display.short_description = _('TSC Number')
    tsc_number_display.admin_order_field = 'tsc_number'

    def is_active_badge(self, obj):
        if obj.is_active:
            return mark_safe('<span class="badge bg-success">✅ Active</span>')
        return mark_safe('<span class="badge bg-secondary">⏹️ Inactive</span>')
    is_active_badge.short_description = _('Status')
    is_active_badge.admin_order_field = 'is_active'

    def date_joined_display(self, obj):
        return obj.date_joined.strftime('%d %b %Y, %H:%M')
    date_joined_display.short_description = _('Joined')
    date_joined_display.admin_order_field = 'date_joined'

    def children_count(self, obj):
        count = obj.children.count()
        if count == 0:
            return mark_safe('<span class="text-muted">0</span>')
        return format_html(
            '<a href="{}?id__in={}">{}</a>',
            reverse('admin:accounts_user_changelist'),
            ','.join(str(c.id) for c in obj.children.all()),
            count
        )
    children_count.short_description = _('Children')
    children_count.admin_order_field = None

    # ---------- Actions ----------
    def activate_users(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'✅ {count} user(s) activated.')
    activate_users.short_description = _('Activate selected users')

    def deactivate_users(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'⏹️ {count} user(s) deactivated.')
    deactivate_users.short_description = _('Deactivate selected users')

    def set_role_to_teacher(self, request, queryset):
        count = queryset.update(role='teacher')
        self.message_user(request, f'👨‍🏫 {count} user(s) set to Teacher.')
    set_role_to_teacher.short_description = _('Set role to Teacher')

    def set_role_to_student(self, request, queryset):
        count = queryset.update(role='student')
        self.message_user(request, f'🧑‍🎓 {count} user(s) set to Student.')
    set_role_to_student.short_description = _('Set role to Student')

    def set_role_to_parent(self, request, queryset):
        count = queryset.update(role='parent')
        self.message_user(request, f'👨‍👩‍👦 {count} user(s) set to Parent.')
    set_role_to_parent.short_description = _('Set role to Parent')

    # ---------- Bulk delete handling ----------
    def delete_queryset(self, request, queryset):
        for user in queryset.prefetch_related('children', 'groups', 'user_permissions'):
            user.children.clear()
            user.groups.clear()
            user.user_permissions.clear()
            try:
                LogEntry.objects.filter(user_id=user.id).delete()
            except Exception:
                pass
        super().delete_queryset(request, queryset)

    # ---------- Field restrictions ----------
    def get_readonly_fields(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return self.readonly_fields + ('role', 'is_staff', 'is_superuser')
        return self.readonly_fields

    def get_fieldsets(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return (
                self.fieldsets[0],
                self.fieldsets[1],
                (_('Permissions'), {
                    'fields': ('is_active',),
                    'description': _('You can only toggle active status.'),
                }),
            )
        return super().get_fieldsets(request, obj)

    # ---------- Form field tweaks ----------
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Make TSC optional in the admin if role is not teacher."""
        if db_field.name == 'tsc_number':
            kwargs['required'] = False
        return super().formfield_for_dbfield(db_field, request, **kwargs)