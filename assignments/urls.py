from django.urls import path
from . import views

app_name = 'assignments'

urlpatterns = [
    # =========================================================================
    # TEACHER ROUTES
    # =========================================================================

    # List all assignments for a batch
    path(
        'batch/<int:batch_id>/',
        views.BatchAssignmentListView.as_view(),
        name='batch_assignments'
    ),

    # Create a new assignment
    path(
        'create/<int:batch_id>/',
        views.AssignmentCreateView.as_view(),
        name='create_assignment'
    ),

    # Update an existing assignment
    path(
        '<int:assignment_id>/update/',
        views.AssignmentUpdateView.as_view(),
        name='update_assignment'
    ),

    # Delete an assignment
    path(
        '<int:assignment_id>/delete/',
        views.AssignmentDeleteView.as_view(),
        name='delete_assignment'
    ),

    # List all submissions for an assignment (grading view)
    path(
        '<int:assignment_id>/submissions/',
        views.AssignmentSubmissionListView.as_view(),
        name='submission_list'
    ),

    # Grade a specific submission
    path(
        'submission/<int:submission_id>/grade/',
        views.GradeSubmissionView.as_view(),
        name='grade_submission'
    ),

    # =========================================================================
    # STUDENT ROUTES
    # =========================================================================

    # List all assignments for a batch (student view)
    path(
        'student/batch/<int:batch_id>/',
        views.StudentBatchAssignmentListView.as_view(),
        name='student_batch_assignments'
    ),

    # View assignment details (with questions & submission status)
    path(
        '<int:assignment_id>/',
        views.AssignmentDetailView.as_view(),
        name='assignment_detail'
    ),

    # Submit (or update) an assignment
    path(
        '<int:assignment_id>/submit/',
        views.AssignmentSubmitView.as_view(),
        name='assignment_submit'
    ),
    path('<int:assignment_id>/submissions/',
        views.AssignmentSubmissionListView.as_view(),
        name='submission_list'
    ),

    path('submission/<int:submission_id>/grade/',
        views.GradeSubmissionView.as_view(),
        name='grade_submission'
        ),
]