from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, FormView, View
)
from django.contrib import messages
from django.db.models import Count, Q, Prefetch, Avg
from django.http import JsonResponse

from accounts.models import User
from batches.models import Batch, Enrollment
from .forms import BatchForm, EnrollmentForm, StudentQuickCreateForm

# Import all mixins from the central common app
from common.mixins import (
    TeacherRequiredMixin,
    StudentRequiredMixin,
    AdminRequiredMixin,
    ParentRequiredMixin,
    TeacherOfBatchMixin,
    StudentEnrolledMixin,
    TeacherOrAdminRequiredMixin,
)
from .forms import LinkParentForm
from content.models import LessonProgress, Lesson

from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

# ============================================================================
# TEACHER – BATCH MANAGEMENT
# ============================================================================

class TeacherBatchListView(LoginRequiredMixin, TeacherRequiredMixin, ListView):
    """
    Dashboard: lists all active batches for the logged‑in teacher.
    """
    model = Batch
    template_name = 'teacher/batch_list.html'
    context_object_name = 'batches'

    def get_queryset(self):
        return Batch.objects.filter(
            teacher=self.request.user,
            is_active=True
        ).prefetch_related(
            'enrollments',
            'lessons',
            'assignments'
        )


class BatchCreateView(LoginRequiredMixin, TeacherRequiredMixin, CreateView):
    """
    Create a new batch. The teacher is automatically assigned.
    """
    model = Batch
    form_class = BatchForm
    template_name = 'teacher/batch_form.html'

    def form_valid(self, form):
        form.instance.teacher = self.request.user
        messages.success(self.request, 'Batch created successfully!')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse('batches:batch_list')


class BatchUpdateView(LoginRequiredMixin, TeacherOfBatchMixin, UpdateView):
    """
    Update an existing batch. Only the batch's teacher can edit.
    """
    model = Batch
    form_class = BatchForm
    template_name = 'teacher/batch_form.html'
    pk_url_kwarg = 'batch_id'

    def form_valid(self, form):
        messages.success(self.request, 'Batch updated successfully.')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse('batches:batch_list')


class BatchDeleteView(LoginRequiredMixin, TeacherOfBatchMixin, DeleteView):
    """
    Delete a batch. Only the batch's teacher can delete.
    """
    model = Batch
    template_name = 'teacher/batch_confirm_delete.html'
    pk_url_kwarg = 'batch_id'

    def get_success_url(self):
        messages.success(self.request, 'Batch deleted successfully.')
        return reverse('batches:batch_list')


class BatchDetailView(LoginRequiredMixin, TeacherOfBatchMixin, DetailView):
    """
    Detailed view of a single batch with enrolled students and statistics.
    """
    model = Batch
    template_name = 'teacher/batch_detail.html'
    pk_url_kwarg = 'batch_id'
    context_object_name = 'batch'

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            Prefetch(
                'enrollments',
                queryset=Enrollment.objects.filter(is_active=True).select_related('student')
            ),
            'lessons',
            'assignments',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch = self.object

        # Enrolled students (active only) – already prefetched
        enrollments = batch.enrollments.filter(is_active=True)
        context['enrollments'] = enrollments
        context['total_students'] = enrollments.count()

        # Lesson and assignment counts – already prefetched
        context['lesson_count'] = batch.lessons.count()
        context['assignment_count'] = batch.assignments.count()

        # Check if batch is full
        context['is_full'] = batch.is_full
        context['available_slots'] = batch.available_slots

        return context


# ============================================================================
# TEACHER – STUDENT ENROLLMENT
# ============================================================================

class BatchEnrollView(LoginRequiredMixin, TeacherOfBatchMixin, FormView):
    """
    Enroll a student into a batch. Supports selecting existing students
    or creating a new student on the fly.
    """
    template_name = 'teacher/enroll_student.html'
    form_class = EnrollmentForm

    def dispatch(self, request, *args, **kwargs):
        self.batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Check if batch is full before enrolling
        if self.batch.is_full:
            messages.error(self.request, 'This batch is already at full capacity.')
            return redirect('batches:batch_detail', batch_id=self.batch.id)

        create_new = form.cleaned_data.get('create_new')

        if create_new:
            # Create a new student account
            student = User.objects.create_user(
                username=form.cleaned_data['username'],
                password='default123',
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                phone=form.cleaned_data.get('phone', ''),
                role='student'
            )
            messages.success(self.request, f"Student {student.get_full_name()} created successfully.")
        else:
            # Use existing student
            student = form.cleaned_data['student']
            if Enrollment.objects.filter(batch=self.batch, student=student).exists():
                messages.warning(self.request, f"{student.get_full_name()} is already enrolled.")
                return redirect('batches:batch_detail', batch_id=self.batch.id)

        # Create the enrollment
        Enrollment.objects.create(batch=self.batch, student=student)
        messages.success(self.request, f"{student.get_full_name()} enrolled successfully.")
        return redirect('batches:batch_detail', batch_id=self.batch.id)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = self.batch
        context['is_full'] = self.batch.is_full
        context['available_slots'] = self.batch.available_slots
        return context


class StudentCreateAndEnrollView(LoginRequiredMixin, TeacherOfBatchMixin, CreateView):
    """
    Create a new student and immediately enrol them in the batch.
    (Alternative to the combined form in BatchEnrollView)
    """
    model = User
    form_class = StudentQuickCreateForm
    template_name = 'teacher/student_create_and_enroll.html'

    def dispatch(self, request, *args, **kwargs):
        self.batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Check if batch is full
        if self.batch.is_full:
            messages.error(self.request, 'This batch is already at full capacity.')
            return redirect('batches:batch_detail', batch_id=self.batch.id)

        student = form.save(commit=False)
        student.role = 'student'
        student.set_password(form.cleaned_data.get('password') or 'default123')
        student.save()

        Enrollment.objects.create(batch=self.batch, student=student)
        messages.success(self.request, f"Student {student.get_full_name()} created and enrolled.")
        return redirect('batches:batch_detail', batch_id=self.batch.id)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = self.batch
        return context


class BatchUnenrollView(LoginRequiredMixin, TeacherOfBatchMixin, View):
    """
    Soft‑delete an enrollment (sets is_active=False).
    Only the batch's teacher can perform this action.
    """
    def post(self, request, batch_id, student_id):
        batch = get_object_or_404(Batch, id=batch_id)
        student = get_object_or_404(User, id=student_id, role='student')
        enrollment = Enrollment.objects.filter(batch=batch, student=student).first()

        if enrollment:
            enrollment.is_active = False
            enrollment.save()
            messages.success(request, f"{student.get_full_name()} has been unenrolled.")
        else:
            messages.error(request, "Student was not enrolled in this batch.")

        return redirect('batches:batch_detail', batch_id=batch.id)


# ============================================================================
# STUDENT – LEARNING DASHBOARD
# ============================================================================

class StudentBatchListView(LoginRequiredMixin, StudentRequiredMixin, ListView):
    """
    Lists all batches the student is actively enrolled in, with progress,
    and calculates the summary dashboard statistics.
    """
    model = Batch
    template_name = 'student/batch_list.html'
    context_object_name = 'enrollments'

    def get_queryset(self):
        return Enrollment.objects.filter(
            student=self.request.user,
            is_active=True
        ).select_related('batch', 'batch__teacher').order_by('-enrolled_on')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollments_qs = self.get_queryset()

        # ------------------------------------------------------------------
        # NEW: Calculate Summary Statistics for Dashboard Cards
        # ------------------------------------------------------------------
        context['batches_count'] = enrollments_qs.count()

        enrolled_batches = [e.batch for e in enrollments_qs]
        all_lessons = Lesson.objects.filter(batch__in=enrolled_batches)
        progress_qs = LessonProgress.objects.filter(
            student=self.request.user,
            lesson__in=all_lessons
        )

        context['lessons_done'] = progress_qs.filter(is_completed=True).count()

        avg_watch = progress_qs.aggregate(avg=Avg('watch_percentage'))['avg']
        context['avg_progress'] = round(avg_watch, 1) if avg_watch is not None else 0.0

        context['teachers_count'] = User.objects.filter(
            batches__in=enrolled_batches,
            role='teacher'
        ).distinct().count()

        # ------------------------------------------------------------------
        # EXISTING: Compute progress for each individual enrollment
        # ------------------------------------------------------------------
        enrollments = []
        for enrollment in enrollments_qs:
            batch = enrollment.batch
            lessons = batch.lessons.all()
            total = lessons.count()

            if total > 0:
                completed = LessonProgress.objects.filter(
                    student=self.request.user,
                    lesson__in=lessons,
                    is_completed=True
                ).count()
                progress_pct = round((completed / total) * 100, 1)
            else:
                completed = 0
                progress_pct = 0

            enrollments.append({
                'enrollment': enrollment,
                'batch': batch,
                'total_lessons': total,
                'completed_lessons': completed,
                'progress': progress_pct,
            })

        context['enrollments'] = enrollments
        return context


class StudentBatchDetailView(LoginRequiredMixin, StudentEnrolledMixin, DetailView):
    """
    Shows a single batch with the student's progress.
    """
    model = Batch
    template_name = 'student/batch_detail.html'
    pk_url_kwarg = 'batch_id'
    context_object_name = 'batch'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch = self.object
        student = self.request.user

        # All lessons in this batch
        lessons = batch.lessons.all().order_by('order', 'created_at')
        total_lessons = lessons.count()

        # Get this student's progress records for the batch
        progress_qs = LessonProgress.objects.filter(
            student=student,
            lesson__batch=batch
        )
        completed_lessons = progress_qs.filter(is_completed=True).count()

        # Build a dict: {lesson_id: LessonProgress}
        progress_map = {p.lesson_id: p for p in progress_qs}

        # Attach progress to each lesson for the template
        lessons_with_progress = []
        for lesson in lessons:
            lessons_with_progress.append({
                'lesson': lesson,
                'progress': progress_map.get(lesson.id),
            })

        # Calculate overall progress percentage
        progress_percentage = (
            round((completed_lessons / total_lessons) * 100, 1)
            if total_lessons else 0
        )

        context['total_lessons'] = total_lessons
        context['completed_lessons'] = completed_lessons
        context['progress_percentage'] = progress_percentage
        context['lessons_with_progress'] = lessons_with_progress

        return context


# ============================================================================
# ADMIN – BATCH OVERSIGHT
# ============================================================================

class AdminBatchListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """
    Admin view of all active batches across the platform.
    """
    model = Batch
    template_name = 'admin/batch_list.html'
    context_object_name = 'batches'

    def get_queryset(self):
        return Batch.objects.filter(is_active=True).select_related(
            'teacher'
        ).prefetch_related(
            'enrollments',
            'lessons',
            'assignments'
        )


class ManageStudentParentsView(LoginRequiredMixin, TeacherRequiredMixin, ListView):
    """
    Display all students enrolled in the teacher's batches with their linked parents.
    Allows the teacher to link/unlink parents.
    """
    template_name = 'teacher/manage_student_parent.html'
    context_object_name = 'students'

    def get_queryset(self):
        # Get all active enrollments for the teacher's batches
        return User.objects.filter(
            role='student',
            enrollments__batch__teacher=self.request.user,
            enrollments__is_active=True
        ).distinct().prefetch_related('parents')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get all active parents for the dropdown
        context['parents'] = User.objects.filter(role='parent', is_active=True).order_by('first_name', 'last_name')
        return context


class UpdateStudentParentView(LoginRequiredMixin, TeacherRequiredMixin, UpdateView):
    model = User
    template_name = 'teacher/update_student_parent.html'
    pk_url_kwarg = 'student_id'
    form_class = LinkParentForm
    context_object_name = 'student'

    def get_form_kwargs(self):
        """Remove 'instance' from kwargs because LinkParentForm is not a ModelForm."""
        kwargs = super().get_form_kwargs()
        kwargs.pop('instance', None)
        return kwargs

    def get_queryset(self):
        return User.objects.filter(
            role='student',
            enrollments__batch__teacher=self.request.user,
            enrollments__is_active=True
        ).distinct()

    def form_valid(self, form):
        student = self.get_object()
        parent = form.cleaned_data['parent']
        student.parents.clear()
        if parent:
            student.parents.add(parent)
            messages.success(self.request, f"Linked {student.get_full_name()} to {parent.get_full_name()}.")
        else:
            messages.success(self.request, f"Unlinked {student.get_full_name()} from all parents.")
        return redirect('batches:manage_student_parents')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['parents'] = User.objects.filter(role='parent', is_active=True).order_by('first_name', 'last_name')
        return context