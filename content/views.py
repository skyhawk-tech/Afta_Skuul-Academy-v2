import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.http import JsonResponse

from batches.models import Batch, Enrollment
from accounts.models import User
from .models import (
    Lesson, LessonProgress,
    LessonQuestion, LessonReply,
)
from .forms import (
    LessonForm,
    LessonQuestionForm, LessonReplyForm,
)


# ============================================================================
# TEACHER – LESSON MANAGEMENT
# ============================================================================

class BatchLessonListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all lessons for a given batch (teacher view)."""
    model = Lesson
    template_name = 'teacher/lesson_list.html'
    context_object_name = 'lessons'

    def test_func(self):
        if not self.request.user.is_authenticated or self.request.user.role != 'teacher':
            return False
        batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return batch.teacher == self.request.user

    def get_queryset(self):
        batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return Lesson.objects.filter(batch=batch).order_by('order', 'created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return context


class LessonCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create a new lesson for a batch."""
    model = Lesson
    form_class = LessonForm
    template_name = 'teacher/lesson_form.html'

    def test_func(self):
        if not self.request.user.is_authenticated or self.request.user.role != 'teacher':
            return False
        batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return batch.teacher == self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return context

    def form_valid(self, form):
        batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        form.instance.batch = batch
        messages.success(self.request, 'Lesson created successfully.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('content:batch_lessons', kwargs={'batch_id': self.kwargs['batch_id']})


class LessonUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update an existing lesson."""
    model = Lesson
    form_class = LessonForm
    template_name = 'teacher/lesson_form.html'
    pk_url_kwarg = 'lesson_id'

    def test_func(self):
        if not self.request.user.is_authenticated or self.request.user.role != 'teacher':
            return False
        lesson = self.get_object()
        return lesson.batch.teacher == self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = self.object.batch
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Lesson updated successfully.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('content:batch_lessons', kwargs={'batch_id': self.object.batch.id})


class LessonDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """Delete a lesson."""
    model = Lesson
    template_name = 'teacher/lesson_confirm_delete.html'
    pk_url_kwarg = 'lesson_id'

    def test_func(self):
        if not self.request.user.is_authenticated or self.request.user.role != 'teacher':
            return False
        lesson = self.get_object()
        return lesson.batch.teacher == self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = self.object.batch
        return context

    def get_success_url(self):
        messages.success(self.request, 'Lesson deleted.')
        return reverse('content:batch_lessons', kwargs={'batch_id': self.object.batch.id})


# ============================================================================
# STUDENT – LESSON VIEWING
# ============================================================================

class StudentBatchLessonListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all released lessons for a batch (student view)."""
    model = Lesson
    template_name = 'student/batch_lessons.html'
    context_object_name = 'lessons'

    def test_func(self):
        if not self.request.user.is_authenticated or self.request.user.role != 'student':
            return False
        return Enrollment.objects.filter(
            student=self.request.user,
            batch_id=self.kwargs['batch_id'],
            is_active=True
        ).exists()

    def get_queryset(self):
        batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return Lesson.objects.filter(batch=batch).order_by('order', 'created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        context['batch'] = batch

        # ---------- Compute progress stats for the new template ----------
        lessons = Lesson.objects.filter(batch=batch)
        total = lessons.count()

        progress_qs = LessonProgress.objects.filter(
            student=self.request.user,
            lesson__batch=batch
        )

        completed = progress_qs.filter(is_completed=True).count()
        in_progress = progress_qs.filter(
            is_completed=False,
            total_watch_seconds__gt=0
        ).count()
        not_started = max(0, total - completed - in_progress)

        context['total_lessons'] = total
        context['completed_lessons'] = completed
        context['in_progress_count'] = in_progress
        context['not_started_count'] = not_started
        context['progress_percentage'] = (
            round((completed / total) * 100, 1) if total else 0
        )

        return context


class LessonDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Display a single lesson with video player and progress.
    Access: enrolled student OR the batch's teacher.
    """
    model = Lesson
    template_name = 'student/lesson_detail.html'
    pk_url_kwarg = 'lesson_id'
    context_object_name = 'lesson'

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False

        lesson = self.get_object()
        user = self.request.user

        # Teacher of this batch?
        if user.role == 'teacher' and lesson.batch.teacher == user:
            return True

        # Enrolled student?
        if user.role == 'student':
            return Enrollment.objects.filter(
                student=user,
                batch=lesson.batch,
                is_active=True
            ).exists()

        return False

    def handle_no_permission(self):
        messages.error(self.request, 'You do not have access to this lesson.')
        if self.request.user.role == 'teacher':
            return redirect('batches:batch_list')
        return redirect('batches:student_batch_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Progress only for students
        if user.role == 'student':
            context['progress'] = LessonProgress.objects.filter(
                student=user,
                lesson=self.object
            ).first()
        else:
            context['progress'] = None

        # Q&A
        context['questions'] = LessonQuestion.objects.filter(
            lesson=self.object
        ).prefetch_related('replies__author', 'student').order_by('-created_at')

        context['question_form'] = LessonQuestionForm()
        context['reply_form'] = LessonReplyForm()
        return context


# ============================================================================
# LIVE CLASS (JITSI)
# ============================================================================

class LiveClassView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Show a live Jitsi Meet class embedded in an iframe.
    Access: the batch's teacher OR an enrolled student.
    """
    model = Lesson
    template_name = 'student/live_class.html'
    pk_url_kwarg = 'lesson_id'
    context_object_name = 'lesson'

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False

        lesson = self.get_object()
        user = self.request.user

        if user.role == 'teacher' and lesson.batch.teacher == user:
            return True

        if user.role == 'student':
            return Enrollment.objects.filter(
                student=user,
                batch=lesson.batch,
                is_active=True
            ).exists()

        return False

    def handle_no_permission(self):
        messages.error(self.request, 'You do not have access to this live class.')
        if self.request.user.role == 'teacher':
            return redirect('batches:batch_list')
        return redirect('batches:student_batch_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lesson = self.object

        if lesson.lesson_type != 'live':
            context['error'] = 'This is not a live lesson.'
            return context

        if not lesson.live_room_name:
            context['error'] = 'Live room has not been set up yet.'
            return context

        now = timezone.now()
        if lesson.live_start and now < lesson.live_start - timedelta(minutes=15):
            context['error'] = (
                f"Class hasn't started yet. It starts in "
                f"{lesson.starts_in_minutes} minutes."
            )
            return context

        if lesson.has_ended:
            context['error'] = 'This live class has already ended.'
            return context

        context['jitsi_room'] = lesson.live_room_name
        context['jitsi_domain'] = 'meet.jit.si'
        context['display_name'] = (
            self.request.user.get_full_name() or self.request.user.username
        )
        context['is_teacher'] = self.request.user.role == 'teacher'

        return context


# ============================================================================
# API – HEARTBEAT (WATCH PROGRESS)
# ============================================================================

class LessonHeartbeatView(LoginRequiredMixin, View):
    """
    Update watch progress for a recorded lesson.
    Expects POST JSON: {"position": <seconds>}
    """

    def post(self, request, lesson_id):
        if not request.user.is_authenticated or request.user.role != 'student':
            return JsonResponse({"error": "Only students can submit progress."}, status=403)

        try:
            lesson = Lesson.objects.get(id=lesson_id)
        except Lesson.DoesNotExist:
            return JsonResponse({"error": "Lesson not found"}, status=404)

        is_enrolled = Enrollment.objects.filter(
            student=request.user,
            batch=lesson.batch,
            is_active=True
        ).exists()
        if not is_enrolled:
            return JsonResponse({"error": "Not enrolled in this batch."}, status=403)

        try:
            data = json.loads(request.body)
            position = int(data.get('position', 0))
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse({"error": "Invalid position"}, status=400)

        if position < 0:
            return JsonResponse({"error": "Position cannot be negative"}, status=400)

        progress, _ = LessonProgress.objects.get_or_create(
            student=request.user,
            lesson=lesson
        )
        progress.update_progress(position)

        return JsonResponse({
            "total_watch_seconds": progress.total_watch_seconds,
            "watch_percentage": round(progress.watch_percentage, 1),
            "is_completed": progress.is_completed,
            "last_position": progress.last_position
        })


# ============================================================================
# TEACHER/ADMIN – ATTENDANCE
# ============================================================================

class LessonAttendanceView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Attendance report for a lesson (teacher/admin only)."""
    model = Lesson
    template_name = 'teacher/attendance_detail.html'
    pk_url_kwarg = 'lesson_id'
    context_object_name = 'lesson'

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.role == 'admin':
            return True
        if self.request.user.role == 'teacher':
            lesson = self.get_object()
            return lesson.batch.teacher == self.request.user
        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lesson = self.object
        batch = lesson.batch

        enrollments = batch.enrollments.filter(is_active=True).select_related('student')
        student_ids = [e.student_id for e in enrollments]
        progress_records = {
            p.student_id: p for p in LessonProgress.objects.filter(
                lesson=lesson, student_id__in=student_ids
            )
        }

        attendance_data = []
        for enrollment in enrollments:
            progress = progress_records.get(enrollment.student_id)
            if progress:
                attended = progress.is_completed
                percentage = progress.watch_percentage
                duration_minutes = progress.total_watch_seconds / 60
            else:
                attended = False
                percentage = 0
                duration_minutes = 0

            attendance_data.append({
                'student': enrollment.student,
                'attended': attended,
                'percentage': round(percentage, 1),
                'duration_minutes': round(duration_minutes, 1),
            })

        context['attendance_data'] = attendance_data
        context['total_enrolled'] = len(attendance_data)
        context['attended_count'] = sum(1 for d in attendance_data if d['attended'])
        return context


# ============================================================================
# Q&A – ASK A QUESTION
# ============================================================================

@login_required
@require_POST
def ask_question(request, lesson_id):
    """Only enrolled students can ask questions."""
    lesson = get_object_or_404(Lesson, id=lesson_id)

    if request.user.role != 'student':
        messages.error(request, 'Only students can post questions.')
        return redirect('content:lesson_detail', lesson_id=lesson.id)

    is_enrolled = Enrollment.objects.filter(
        student=request.user,
        batch=lesson.batch,
        is_active=True
    ).exists()
    if not is_enrolled:
        messages.error(request, 'You are not enrolled in this batch.')
        return redirect('content:lesson_detail', lesson_id=lesson.id)

    form = LessonQuestionForm(request.POST)
    if form.is_valid():
        question = form.save(commit=False)
        question.lesson = lesson
        question.student = request.user
        question.save()
        messages.success(request, 'Your question has been posted.')
    else:
        messages.error(request, 'Your question could not be posted.')

    return redirect('content:lesson_detail', lesson_id=lesson.id)


# ============================================================================
# Q&A – REPLY TO A QUESTION
# ============================================================================

@login_required
@require_POST
def reply_to_question(request, question_id):
    """Any enrolled student or the batch's teacher can reply."""
    question = get_object_or_404(LessonQuestion, id=question_id)
    lesson = question.lesson
    batch = lesson.batch
    user = request.user

    can_reply = False
    if user.role == 'teacher' and batch.teacher == user:
        can_reply = True
    elif user.role == 'student':
        can_reply = Enrollment.objects.filter(
            student=user, batch=batch, is_active=True
        ).exists()

    if not can_reply:
        messages.error(request, 'You cannot reply to this question.')
        return redirect('content:lesson_detail', lesson_id=lesson.id)

    form = LessonReplyForm(request.POST)
    if form.is_valid():
        reply = form.save(commit=False)
        reply.question = question
        reply.author = user
        reply.save()
        messages.success(request, 'Your reply has been posted.')
    else:
        messages.error(request, 'Your reply could not be posted.')

    return redirect('content:lesson_detail', lesson_id=lesson.id)


# ============================================================================
# LIVE CLASS – ATTENDANCE PINGS
# ============================================================================

@login_required
@require_POST
def live_join(request, lesson_id):
    """
    Called when a student opens the live class page.
    Creates or updates their LessonProgress record.
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)

    if lesson.lesson_type != 'live':
        return JsonResponse({"error": "Not a live lesson"}, status=400)

    if request.user.role != 'student':
        return JsonResponse({"status": "teacher"}, status=200)

    is_enrolled = Enrollment.objects.filter(
        student=request.user, batch=lesson.batch, is_active=True
    ).exists()
    if not is_enrolled:
        return JsonResponse({"error": "Not enrolled"}, status=403)

    progress, created = LessonProgress.objects.get_or_create(
        student=request.user,
        lesson=lesson
    )
    progress.add_live_time(1)

    return JsonResponse({
        "status": "joined",
        "attended_seconds": progress.total_watch_seconds,
    })


@login_required
@require_POST
def live_heartbeat(request, lesson_id):
    """
    Called every 60 seconds while the student is in the live class.
    Payload: {"seconds": 60}
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)

    if request.user.role != 'student':
        return JsonResponse({"status": "teacher"})

    try:
        data = json.loads(request.body)
        seconds = int(data.get('seconds', 60))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({"error": "Invalid payload"}, status=400)

    progress, _ = LessonProgress.objects.get_or_create(
        student=request.user,
        lesson=lesson
    )
    progress.add_live_time(seconds)

    return JsonResponse({
        "attended_seconds": progress.total_watch_seconds,
        "is_completed": progress.is_completed,
    })


@login_required
@require_POST
def live_leave(request, lesson_id):
    """
    Called when the student closes the live class tab.
    Records one final second so the ping registers.
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)

    if request.user.role != 'student':
        return JsonResponse({"status": "teacher"})

    progress, _ = LessonProgress.objects.get_or_create(
        student=request.user,
        lesson=lesson
    )
    progress.add_live_time(1)

    return JsonResponse({"status": "left"})