from django.urls import path
from . import views

app_name = 'content'

urlpatterns = [
    # Teacher: list lessons for a batch
    path('batch/<int:batch_id>/', views.BatchLessonListView.as_view(), name='batch_lessons'),

    # Teacher: create lesson
    path('create/<int:batch_id>/', views.LessonCreateView.as_view(), name='create_lesson'),

    # Teacher: update/delete lesson
    path('<int:lesson_id>/update/', views.LessonUpdateView.as_view(), name='update_lesson'),
    path('<int:lesson_id>/delete/', views.LessonDeleteView.as_view(), name='delete_lesson'),

    # Student: view lesson (video player)
    path('<int:lesson_id>/', views.LessonDetailView.as_view(), name='lesson_detail'),

    # Student: heartbeat for watch progress
    path('<int:lesson_id>/heartbeat/', views.LessonHeartbeatView.as_view(), name='lesson_heartbeat'),

    # Teacher/Admin: attendance summary
    path('<int:lesson_id>/attendance/', views.LessonAttendanceView.as_view(), name='lesson_attendance'),

    # Student: list lessons for a batch (alternate view)
    path('student/batch/<int:batch_id>/', views.StudentBatchLessonListView.as_view(), name='student_batch_lessons'),
    
    path('<int:lesson_id>/ask/', views.ask_question, name='ask_question'),
    path('question/<int:question_id>/reply/', views.reply_to_question, name='reply_to_question'),
    
    path('<int:lesson_id>/live/', views.LiveClassView.as_view(), name='live_class'),
    # Live class attendance endpoints
    path('<int:lesson_id>/live/join/', views.live_join, name='live_join'),
    path('<int:lesson_id>/live/heartbeat/', views.live_heartbeat, name='live_heartbeat'),
    path('<int:lesson_id>/live/leave/', views.live_leave, name='live_leave'),
]