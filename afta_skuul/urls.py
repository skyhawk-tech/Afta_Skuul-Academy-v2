"""
URL configuration for afta_skuul project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from accounts.views import AboutUsView



def home_redirect(request):
    """
    Root URL view. Redirects users to their appropriate dashboard 
    based on their role, or to the login page if not authenticated.
    """
    if not request.user.is_authenticated:
        return redirect('accounts:login')  # Ensure 'accounts:login' is your login URL name

    # Redirect based on role
    if request.user.role == 'teacher':
        return redirect('batches:batch_list')  # Teacher dashboard
    elif request.user.role == 'student':
        return redirect('batches:student_batch_list')  # Student dashboard
    elif request.user.role == 'parent':
        # Assuming you have a parent dashboard in analytics
        return redirect('analytics:parent_analytics') 
    elif request.user.role == 'admin':
        return redirect('analytics:admin_dashboard')

    # Fallback if role is unknown
    return redirect('accounts:login')


urlpatterns = [
    path('admin/', admin.site.urls),
    
    # FIXED: Changed name='root' to name='home' so it matches the redirect target
    path('', home_redirect, name='home'),
    
    path('accounts/', include('accounts.urls')),
    path('assignments/', include('assignments.urls')),
    path('batches/', include('batches.urls')),
    path('content/', include('content.urls')),
    path('', include('analytics.urls')),
    path('about/', AboutUsView.as_view(), name='about_us'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)