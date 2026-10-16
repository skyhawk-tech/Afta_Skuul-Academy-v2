from django.urls import path
from .views import (HomeView, LoginView, LogoutView, RegisterView,
                    ProfileView, CustomPasswordChangeView, AboutUsView)
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('password-change/', CustomPasswordChangeView.as_view(), name='password_change'),
    path('about/', AboutUsView.as_view(), name='about_us'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
]