from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('admin-panel/dashboard/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('teacher/dashboard/', views.TeacherAnalyticsView.as_view(), name='teacher_analytics'),
    path('parent/dashboard/', views.ParentAnalyticsView.as_view(), name='parent_analytics'),
]