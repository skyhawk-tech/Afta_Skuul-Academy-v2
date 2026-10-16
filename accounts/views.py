from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as AuthLoginView, LogoutView as AuthLogoutView, PasswordChangeView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, TemplateView
from django.contrib import messages

from .forms import UserRegistrationForm, UserProfileForm
from .models import User


# ============================================================================
# HOME – ROLE‑BASED REDIRECT
# ============================================================================

class HomeView(LoginRequiredMixin, TemplateView):
    """
    Redirect authenticated users to their role‑specific dashboard.
    """
    def dispatch(self, request, *args, **kwargs):
        role = getattr(request.user, 'role', None)

        if role == 'admin':
            return redirect('analytics:admin_dashboard')
        elif role == 'teacher':
            return redirect('batches:batch_list')
        elif role == 'student':
            return redirect('batches:student_batch_list')
        elif role == 'parent':
            return redirect('analytics:parent_analytics')

        # Fallback: should never happen, but safe guard
        return redirect('accounts:login')


# ============================================================================
# LOGIN / LOGOUT
# ============================================================================

class LoginView(AuthLoginView):
    """
    Custom login view with a redirect to home after login.
    """
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('home')


class LogoutView(AuthLogoutView):
    """
    Custom logout view. Redirects to the login page.
    """
    next_page = 'accounts:login'


# ============================================================================
# REGISTRATION
# ============================================================================

class RegisterView(CreateView):
    """
    Allow any user to register as student, teacher, or parent.
    After registration, the user is automatically logged in.
    """
    model = User
    form_class = UserRegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('home')

    def dispatch(self, request, *args, **kwargs):
        """Prevent logged‑in users from accessing the registration page."""
        if request.user.is_authenticated:
            return redirect('home')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.instance
        login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(self.request, f'Welcome, {user.get_full_name()}!')
        return response


# ============================================================================
# PROFILE
# ============================================================================

class ProfileView(LoginRequiredMixin, UpdateView):
    """
    Allow authenticated users to update their own profile.
    """
    model = User
    form_class = UserProfileForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('profile')

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Profile updated successfully.')
        return super().form_valid(form)


# ============================================================================
# PASSWORD CHANGE
# ============================================================================

class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """
    Built‑in password change view with a custom template and success message.
    """
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('profile')

    def form_valid(self, form):
        messages.success(self.request, 'Your password has been changed.')
        return super().form_valid(form)


# ============================================================================
# STATIC PAGES
# ============================================================================

class AboutUsView(TemplateView):
    """
    Simple static page for 'About Us'.
    """
    template_name = 'about_us.html'