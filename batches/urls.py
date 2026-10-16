from django.urls import path
from . import views

app_name = 'batches'

urlpatterns = [
    # Teacher batch management
    path('', views.TeacherBatchListView.as_view(), name='batch_list'),  # teacher dashboard
    path('create/', views.BatchCreateView.as_view(), name='create_batch'),
    path('<int:batch_id>/update/', views.BatchUpdateView.as_view(), name='update_batch'),
    path('<int:batch_id>/delete/', views.BatchDeleteView.as_view(), name='delete_batch'),
    path('<int:batch_id>/', views.BatchDetailView.as_view(), name='batch_detail'),

    # Enrollment
    path('<int:batch_id>/enroll/', views.BatchEnrollView.as_view(), name='enroll_student'),
    path('<int:batch_id>/unenroll/<int:student_id>/', views.BatchUnenrollView.as_view(), name='unenroll_student'),
    path('<int:batch_id>/create-and-enroll/', views.StudentCreateAndEnrollView.as_view(), name='create_and_enroll'),
    #path('<int:batch_id>/bulk-enroll/', views.BulkEnrollView.as_view(), name='bulk_enroll'),

    # Student views
    path('student/', views.StudentBatchListView.as_view(), name='student_batch_list'),
    path('student/<int:batch_id>/', views.StudentBatchDetailView.as_view(), name='student_batch_detail'),

    # Admin view
    path('admin/all/', views.AdminBatchListView.as_view(), name='admin_batch_list'),
    
    # Parent linking
    path('manage-parents/', views.ManageStudentParentsView.as_view(), name='manage_student_parents'),
    path('student/<int:student_id>/update-parent/', views.UpdateStudentParentView.as_view(), name='update_student_parent'),
]