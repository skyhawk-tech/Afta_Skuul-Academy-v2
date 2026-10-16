from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.forms import UserChangeForm
# Project imports
from batches.models import Batch, Enrollment
from accounts.models import User

# App imports
from .models import Assignment, Submission
from .forms import AssignmentForm, GradeForm

# Common mixins
from common.mixins import (
    TeacherOfBatchMixin,
    StudentEnrolledMixin,
    TeacherRequiredMixin,
    StudentRequiredMixin,
)


# ============================================================================
# TEACHER – ASSIGNMENT MANAGEMENT
# ============================================================================

class BatchAssignmentListView(LoginRequiredMixin, TeacherOfBatchMixin, ListView):
    """List assignments for a batch (uses batch_id from URL)."""
    model = Assignment
    template_name = 'assignments/assignment_list.html'
    context_object_name = 'assignments'

    def dispatch(self, request, *args, **kwargs):
        self.batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Assignment.objects.filter(batch=self.batch).order_by('-due_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = self.batch
        return context


class AssignmentCreateView(LoginRequiredMixin, TeacherOfBatchMixin, CreateView):
    """Create a new assignment (uses batch_id from URL)."""
    model = Assignment
    form_class = AssignmentForm
    template_name = 'assignments/assignment_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = self.batch
        return context

    def form_valid(self, form):
        form.instance.batch = self.batch
        messages.success(self.request, 'Assignment created successfully.')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse('assignments:batch_assignments',
                       kwargs={'batch_id': self.batch.id})


class AssignmentUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update an assignment – custom ownership check."""
    model = Assignment
    form_class = AssignmentForm
    template_name = 'assignments/assignment_form.html'
    pk_url_kwarg = 'assignment_id'

    def test_func(self):
        if not self.request.user.is_authenticated or self.request.user.role != 'teacher':
            return False
        assignment = self.get_object()
        return assignment.batch.teacher == self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = self.object.batch
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Assignment updated successfully.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('assignments:batch_assignments',
                       kwargs={'batch_id': self.object.batch.id})


class AssignmentDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """Delete an assignment – custom ownership check."""
    model = Assignment
    template_name = 'assignments/assignment_confirm_delete.html'
    pk_url_kwarg = 'assignment_id'

    def test_func(self):
        if not self.request.user.is_authenticated or self.request.user.role != 'teacher':
            return False
        assignment = self.get_object()
        return assignment.batch.teacher == self.request.user

    def get_success_url(self):
        messages.success(self.request, 'Assignment deleted successfully.')
        return reverse('assignments:batch_assignments',
                       kwargs={'batch_id': self.object.batch.id})


class AssignmentSubmissionListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List submissions for an assignment – custom ownership check."""
    model = Submission
    template_name = 'assignments/submission_list.html'
    context_object_name = 'submissions'

    def test_func(self):
        if not self.request.user.is_authenticated or self.request.user.role != 'teacher':
            return False
        assignment = get_object_or_404(Assignment, id=self.kwargs['assignment_id'])
        return assignment.batch.teacher == self.request.user

    def get_queryset(self):
        self.assignment = get_object_or_404(Assignment, id=self.kwargs['assignment_id'])
        return Submission.objects.filter(
            assignment=self.assignment
        ).select_related('student').order_by('-submitted_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        context['assignment'] = self.assignment
        context['graded_count'] = qs.filter(marks_obtained__isnull=False).count()
        context['pending_count'] = qs.filter(marks_obtained__isnull=True).count()
        return context


class GradeSubmissionView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Grade a submission – custom ownership check."""
    model = Submission
    form_class = GradeForm
    template_name = 'assignments/grade_form.html'
    pk_url_kwarg = 'submission_id'

    def test_func(self):
        if not self.request.user.is_authenticated or self.request.user.role != 'teacher':
            return False
        submission = self.get_object()
        return submission.assignment.batch.teacher == self.request.user

    def form_valid(self, form):
        form.instance.graded_by = self.request.user
        form.instance.graded_at = timezone.now()
        messages.success(self.request, 'Grade submitted successfully.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('assignments:submission_list',
                       kwargs={'assignment_id': self.object.assignment.id})
# ============================================================================
# STUDENT – ASSIGNMENT VIEWING & SUBMISSION
# ============================================================================

class StudentBatchAssignmentListView(LoginRequiredMixin, StudentEnrolledMixin, ListView):
    """
    Display all assignments for a batch (student view).
    """
    model = Assignment
    template_name = 'assignments/student_batch_assignments.html'
    context_object_name = 'assignments'

    def dispatch(self, request, *args, **kwargs):
        self.batch = get_object_or_404(Batch, id=self.kwargs['batch_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Assignment.objects.filter(batch=self.batch).order_by('-due_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['batch'] = self.batch
        
        # 1. Get all assignments for this batch
        assignments = context['assignments']
        
        # 2. Fetch all submissions for this student for these assignments
        student_submissions = Submission.objects.filter(
            student=self.request.user,
            assignment__in=assignments
        )
        
        # 3. Create a dictionary: {assignment_id: submission_instance}
        submission_map = {sub.assignment_id: sub for sub in student_submissions}
        
        # 4. Attach the submission and overdue status to each assignment
        assignment_data = []
        for assignment in assignments:
            assignment_data.append({
                'assignment': assignment,
                'submission': submission_map.get(assignment.id), # Will be None if not submitted
                'is_overdue': assignment.is_overdue, # Assuming this is a property on your model
            })
            
        context['assignment_data'] = assignment_data
        return context

class AssignmentDetailView(LoginRequiredMixin, DetailView):
    model = Assignment
    template_name = 'assignments/assignment_detail.html'
    pk_url_kwarg = 'assignment_id'
    context_object_name = 'assignment'

    def dispatch(self, request, *args, **kwargs):
        assignment = get_object_or_404(Assignment, id=self.kwargs['assignment_id'])
        is_enrolled = Enrollment.objects.filter(
            student=request.user,
            batch=assignment.batch,
            is_active=True
        ).exists()
        if not is_enrolled:
            messages.error(request, 'You are not enrolled in this batch.')
            return redirect('batches:student_batch_list')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        submission = Submission.objects.filter(
            student=self.request.user,
            assignment=self.object
        ).first()
        context['submission'] = submission

        # Can the student answer now?
        context['can_submit'] = (
            not submission and not self.object.is_overdue
        ) or (
            submission and not self.object.is_overdue
            and submission.marks_obtained is None
        )

        # Attach student answers to each question
        questions = []
        for q in self.object.questions:
            q_copy = q.copy()
            if submission:
                q_copy['student_answer'] = submission.answers.get(str(q.get('id')), None)
            else:
                q_copy['student_answer'] = None
            questions.append(q_copy)
        context['questions'] = questions

        return context

    def post(self, request, *args, **kwargs):
        """Handle direct submission from the detail page."""
        assignment = get_object_or_404(Assignment, id=self.kwargs['assignment_id'])

        if assignment.is_overdue:
            messages.error(request, 'This assignment is overdue. Submissions are closed.')
            return redirect('assignments:assignment_detail', assignment_id=assignment.id)

        submission, _ = Submission.objects.get_or_create(
            student=request.user,
            assignment=assignment
        )

        # Collect answers
        answers = {}
        for q in assignment.questions:
            q_id = str(q.get('id'))
            if q.get('type') in ['mcq', 'short']:
                answers[q_id] = request.POST.get(f'q_{q_id}', '')

        if 'file_upload' in request.FILES:
            submission.file_upload = request.FILES['file_upload']

        submission.answers = answers
        submission.save()

        messages.success(request, 'Your submission has been saved.')
        return redirect('assignments:assignment_detail', assignment_id=assignment.id)


class AssignmentSubmitView(LoginRequiredMixin,  View):
    """
    Handles assignment submission:
    - GET: shows the form with per-question inputs
    - POST: saves answers to Submission.answers (JSON) and file_upload
    """

    def get(self, request, *args, **kwargs):
        assignment = get_object_or_404(Assignment, id=self.kwargs['assignment_id'])

        # Block if overdue
        if assignment.is_overdue:
            messages.error(request, 'This assignment is overdue. Submissions are closed.')
            return redirect('assignments:assignment_detail', assignment_id=assignment.id)

        # Get or create submission
        submission, _ = Submission.objects.get_or_create(
            student=request.user,
            assignment=assignment
        )

        context = {
            'assignment': assignment,
            'submission': submission,
            'existing_answers': submission.answers or {},
        }
        return render(request, 'assignments/assignment_submit.html', context)

    def post(self, request, *args, **kwargs):
        assignment = get_object_or_404(Assignment, id=self.kwargs['assignment_id'])

        # Block if overdue
        if assignment.is_overdue:
            messages.error(request, 'This assignment is overdue. Submissions are closed.')
            return redirect('assignments:assignment_detail', assignment_id=assignment.id)

        # Get or create submission
        submission, _ = Submission.objects.get_or_create(
            student=request.user,
            assignment=assignment
        )

        # Collect answers from POST data
        answers = {}
        for q in assignment.questions:
            q_id = str(q.get('id'))
            if q.get('type') in ['mcq', 'short']:
                answers[q_id] = request.POST.get(f'q_{q_id}', '')

        # General file upload
        if 'file_upload' in request.FILES:
            submission.file_upload = request.FILES['file_upload']

        submission.answers = answers
        submission.save()

        messages.success(request, 'Your submission has been saved.')
        return redirect('assignments:assignment_detail', assignment_id=assignment.id)
    
class ProfileView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserChangeForm # or your custom UserUpdateForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('accounts:profile')
    
    def get_object(self):
        return self.request.user