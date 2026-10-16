from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from batches.models import Batch, Enrollment


# ============================================================================
# BASIC ROLE MIXINS
# ============================================================================

class TeacherRequiredMixin(UserPassesTestMixin):
    """
    Require the user to be authenticated and have the role 'teacher'.

    Usage:
        class MyView(LoginRequiredMixin, TeacherRequiredMixin, View):
            ...
    """
    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.role == 'teacher'

    def handle_no_permission(self):
        """Redirect with an error message when permission is denied."""
        if self.request.user.is_authenticated:
            messages.error(self.request, "You do not have teacher permissions.")
            return redirect('home')
        return super().handle_no_permission()


class StudentRequiredMixin(UserPassesTestMixin):
    """
    Require the user to be authenticated and have the role 'student'.
    """
    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.role == 'student'

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "You do not have student permissions.")
            return redirect('home')
        return super().handle_no_permission()


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Require the user to be authenticated and have the role 'admin'.
    """
    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.role == 'admin'

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "You do not have admin permissions.")
            return redirect('home')
        return super().handle_no_permission()


class ParentRequiredMixin(UserPassesTestMixin):
    """
    Require the user to be authenticated and have the role 'parent'.
    """
    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.role == 'parent'

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "You do not have parent permissions.")
            return redirect('home')
        return super().handle_no_permission()


class TeacherOrAdminRequiredMixin(UserPassesTestMixin):
    """
    Require the user to be authenticated and have either 'teacher' or 'admin' role.
    """
    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.role in ['admin', 'teacher']

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "You need teacher or admin permissions.")
            return redirect('home')
        return super().handle_no_permission()


# ============================================================================
# OBJECT OWNERSHIP MIXINS
# ============================================================================

class TeacherOfBatchMixin(UserPassesTestMixin):
    """
    Verify that the current teacher owns the specified batch.

    Supports:
    - 'batch_id' URL kwarg
    - 'pk' URL kwarg (for generic DetailView)
    - 'get_object()' method (for object-based views)

    Caches the result for 60 seconds to reduce database queries.
    """
    def test_func(self) -> bool:
        if not self.request.user.is_authenticated or self.request.user.role != 'teacher':
            return False

        # Try to get the batch
        batch = self._get_batch()
        if batch is None:
            return False

        # Cache the result for this user and batch
        cache_key = f'teacher_of_batch_{self.request.user.id}_{batch.id}'
        result = cache.get(cache_key)
        if result is None:
            result = batch.teacher_id == self.request.user.id
            cache.set(cache_key, result, 60)  # Cache for 60 seconds

        return result

    def _get_batch(self):
        """Helper to extract the batch from various sources."""
        # From URL kwargs
        batch_id = self.kwargs.get('batch_id') or self.kwargs.get('pk')
        if batch_id is not None:
            return get_object_or_404(Batch, id=batch_id)

        # From the object (if get_object() exists)
        if hasattr(self, 'get_object'):
            obj = self.get_object()
            if hasattr(obj, 'batch'):
                return obj.batch
            elif hasattr(obj, 'teacher') and isinstance(obj, Batch):
                return obj

        return None

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "You do not own this batch.")
            return redirect('home')
        return super().handle_no_permission()


class StudentEnrolledMixin(UserPassesTestMixin):
    """
    Verify that the current student is enrolled in the specified batch.

    Supports:
    - 'batch_id' URL kwarg
    - 'get_object()' method (for object-based views)

    Caches the result for 60 seconds to reduce database queries.
    """
    def test_func(self) -> bool:
        if not self.request.user.is_authenticated or self.request.user.role != 'student':
            return False

        # Try to get the batch
        batch = self._get_batch()
        if batch is None:
            return False

        # Cache the result for this user and batch
        cache_key = f'student_enrolled_{self.request.user.id}_{batch.id}'
        result = cache.get(cache_key)
        if result is None:
            result = Enrollment.objects.filter(
                student=self.request.user,
                batch=batch,
                is_active=True
            ).exists()
            cache.set(cache_key, result, 60)

        return result

    def _get_batch(self):
        """Helper to extract the batch from various sources."""
        # From URL kwargs
        batch_id = self.kwargs.get('batch_id')
        if batch_id is not None:
            return get_object_or_404(Batch, id=batch_id)

        # From the object (if get_object() exists)
        if hasattr(self, 'get_object'):
            obj = self.get_object()
            if hasattr(obj, 'batch'):
                return obj.batch
            elif hasattr(obj, 'batch_id'):
                return get_object_or_404(Batch, id=obj.batch_id)
            elif isinstance(obj, Batch):
                return obj

        return None

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "You are not enrolled in this batch.")
            return redirect('home')
        return super().handle_no_permission()


class OwnsObjectMixin(UserPassesTestMixin):
    """
    Generic mixin to verify that the current user owns an object.

    Usage:
        class MyView(OwnsObjectMixin):
            owner_field = 'teacher'  # The field name on the object
            model = Batch
            object_key = 'batch_id'

    Override _get_object() if you need custom retrieval.
    """
    owner_field: str = None
    model = None
    object_key: str = 'pk'
    redirect_url: str = 'home'

    def test_func(self) -> bool:
        if not self.request.user.is_authenticated:
            return False

        obj = self._get_object()
        if obj is None:
            return False

        owner = getattr(obj, self.owner_field, None)
        if owner is None:
            return False

        return owner == self.request.user

    def _get_object(self):
        """Retrieve the object from the database."""
        obj_id = self.kwargs.get(self.object_key)
        if obj_id is None or self.model is None:
            return None

        try:
            return self.model.objects.get(id=obj_id)
        except self.model.DoesNotExist:
            return None

    def handle_no_permission(self):
        messages.error(self.request, "You do not have permission to access this resource.")
        return redirect(self.redirect_url)


# ============================================================================
# GENERIC MIXINS
# ============================================================================

class LoginAndRoleRequiredMixin(UserPassesTestMixin):
    """
    Generic mixin that requires a specific role.

    Usage:
        class MyView(LoginAndRoleRequiredMixin):
            role_required = 'teacher'
    """
    role_required: str = None

    def test_func(self) -> bool:
        if not self.request.user.is_authenticated:
            return False
        if self.role_required:
            return self.request.user.role == self.role_required
        return True

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            role_name = self.role_required.capitalize() if self.role_required else ''
            messages.error(self.request, f"You need {role_name} permissions.")
            return redirect('home')
        return super().handle_no_permission()


class MultipleRolesRequiredMixin(UserPassesTestMixin):
    """
    Require the user to have one of the specified roles.

    Usage:
        class MyView(MultipleRolesRequiredMixin):
            allowed_roles = ['teacher', 'admin']
    """
    allowed_roles: list = []

    def test_func(self) -> bool:
        if not self.request.user.is_authenticated:
            return False
        if self.allowed_roles:
            return self.request.user.role in self.allowed_roles
        return False

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            roles = ', '.join(self.allowed_roles)
            messages.error(self.request, f"You need one of these roles: {roles}.")
            return redirect('home')
        return super().handle_no_permission()


class UserIsActiveMixin(UserPassesTestMixin):
    """
    Require the user account to be active.

    Usage:
        class MyView(UserIsActiveMixin, View):
            ...
    """
    def test_func(self) -> bool:
        if not self.request.user.is_authenticated:
            return False
        return self.request.user.is_active

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "Your account is inactive. Please contact support.")
            return redirect('login')
        return super().handle_no_permission()