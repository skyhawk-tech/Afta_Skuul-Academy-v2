import json
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Assignment, Submission

User = get_user_model()


# ============================================================================
# CUSTOM VALIDATORS
# ============================================================================

def validate_file_size(file, max_mb=20):
    """Validate file size does not exceed the given limit."""
    if file.size > max_mb * 1024 * 1024:
        raise ValidationError(_(f'File size exceeds {max_mb} MB limit.'))


def validate_file_extension(file, allowed_extensions):
    """Validate file extension against a list of allowed extensions."""
    ext = file.name.split('.')[-1].lower()
    if ext not in allowed_extensions:
        raise ValidationError(
            _(f'Unsupported file type. Allowed: {", ".join(allowed_extensions)}.')
        )


# ============================================================================
# ASSIGNMENT FORM
# ============================================================================

class AssignmentForm(forms.ModelForm):
    """
    Form for creating and editing assignments.
    Includes validation for due date, marks, and questions (JSON).
    """

    class Meta:
        model = Assignment
        fields = [
            'title', 'description', 'type', 'total_marks',
            'due_date', 'time_limit_minutes', 'questions'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Enter assignment title'),
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': _('Describe the assignment...'),
            }),
            'type': forms.Select(attrs={
                'class': 'form-select',
            }),
            'total_marks': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'placeholder': _('e.g., 10'),
            }),
            'due_date': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control',
            }),
            'time_limit_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': _('Optional (e.g., 60)'),
            }),
            'questions': forms.Textarea(attrs={
                'rows': 8,
                'class': 'form-control font-monospace',
                'placeholder': _(
                    'Enter questions as JSON:\n'
                    '[\n'
                    '  {"id": 1, "type": "mcq", "question": "...", "options": ["A","B"], "answer": "A", "marks": 1},\n'
                    '  {"id": 2, "type": "short", "question": "...", "marks": 2}\n'
                    ']'
                ),
            }),
        }
        labels = {
            'title': _('Title'),
            'description': _('Description'),
            'type': _('Assignment Type'),
            'total_marks': _('Total Marks'),
            'due_date': _('Due Date'),
            'time_limit_minutes': _('Time Limit (minutes)'),
            'questions': _('Questions (JSON)'),
        }
        help_texts = {
            'time_limit_minutes': _('Leave blank for no time limit.'),
            'questions': _('Provide questions in valid JSON format.'),
        }

    def __init__(self, *args, **kwargs):  # FIXED: Double underscores
        super()._init_(*args, **kwargs)
        # Mark required fields
        self.fields['title'].required = True
        self.fields['total_marks'].required = True
        self.fields['due_date'].required = True
        
        # FIXED: Make questions optional so [] is accepted
        self.fields['questions'].required = False

    # ---------- Field validation ----------
    def clean_due_date(self):
        due_date = self.cleaned_data.get('due_date')
        if due_date and due_date < timezone.now():
            raise ValidationError(_('Due date cannot be in the past.'))
        return due_date

    def clean_total_marks(self):
        total_marks = self.cleaned_data.get('total_marks')
        if total_marks is not None and total_marks <= 0:
            raise ValidationError(_('Total marks must be greater than zero.'))
        return total_marks

    def clean_questions(self):
        questions = self.cleaned_data.get('questions')
        if not questions:
            return []  # Return empty list instead of None

        if isinstance(questions, str):
            try:
                parsed = json.loads(questions)
            except json.JSONDecodeError as e:
                raise ValidationError(_(f'Invalid JSON format: {e}'))
        elif isinstance(questions, list):
            parsed = questions
        else:
            raise ValidationError(_('Questions must be a JSON list of objects.'))

        if not isinstance(parsed, list):
            raise ValidationError(_('Questions must be a list of objects.'))

        for i, q in enumerate(parsed):
            if not isinstance(q, dict):
                raise ValidationError(_(f'Question {i+1} must be an object.'))
            if 'id' not in q:
                raise ValidationError(_(f'Question {i+1} is missing an "id".'))
            if 'type' not in q:
                raise ValidationError(_(f'Question {i+1} is missing a "type".'))
            if q['type'] not in ['mcq', 'short', 'file']:
                raise ValidationError(_(f'Question {i+1} has invalid type: "{q["type"]}".'))
            if q['type'] == 'mcq':
                if 'options' not in q or not q['options']:
                    raise ValidationError(_(f'MCQ question {i+1} must have "options".'))
                if 'answer' not in q:
                    raise ValidationError(_(f'MCQ question {i+1} must have an "answer".'))

        return parsed

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data


# ============================================================================
# SUBMISSION FORM
# ============================================================================

class SubmissionForm(forms.ModelForm):
    """
    Form for students to submit assignments (file upload + answers).
    Validates that at least one of file or answers is provided.
    """

    class Meta:
        model = Submission
        fields = ['file_upload', 'answers']
        widgets = {
            'file_upload': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png,.txt',
            }),
            'answers': forms.Textarea(attrs={
                'rows': 5,
                'class': 'form-control font-monospace',
                'placeholder': _(
                    'Enter answers as JSON, e.g.:\n'
                    '{"1": "A", "2": "Paris", "3": null}'
                ),
            }),
        }
        labels = {
            'file_upload': _('Upload File'),
            'answers': _('Answers (JSON)'),
        }
        help_texts = {
            'file_upload': _('Upload a photo, PDF, Word document, or text file.'),
            'answers': _('Provide answers in JSON format keyed by question ID.'),
        }

    def _init_(self, *args, **kwargs):
        super()._init_(*args, **kwargs)
        # Ensure at least one of file or answers is required – done in clean()

    def clean_file_upload(self):
        file = self.cleaned_data.get('file_upload')
        if file:
            # Validate size (20 MB)
            validate_file_size(file, max_mb=20)
            # Validate extension
            allowed = ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'txt']
            validate_file_extension(file, allowed)
        return file

    def clean_answers(self):
        answers = self.cleaned_data.get('answers')
        if answers:
            # Attempt to parse JSON to ensure it's valid
            try:
                parsed = json.loads(answers)
                if not isinstance(parsed, dict):
                    raise ValidationError(_('Answers must be a JSON object (dictionary).'))
                return parsed  # Store as dict
            except json.JSONDecodeError as e:
                raise ValidationError(_(f'Invalid JSON format: {e}'))
        return answers

    def clean(self):
        cleaned_data = super().clean()
        file_upload = cleaned_data.get('file_upload')
        answers = cleaned_data.get('answers')

        if not file_upload and not answers:
            raise ValidationError(_('You must provide either a file upload or answer text.'))

        return cleaned_data


# ============================================================================
# GRADING FORM
# ============================================================================

class GradeForm(forms.ModelForm):
    """
    Form for teachers to grade submissions.
    Validates that marks do not exceed the total marks of the assignment.
    """

    class Meta:
        model = Submission
        fields = ['marks_obtained', 'feedback']
        widgets = {
            'marks_obtained': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.5',
                'min': 0,
                'placeholder': _('Enter marks'),
            }),
            'feedback': forms.Textarea(attrs={
                'rows': 4,
                'class': 'form-control',
                'placeholder': _('Provide feedback for the student...'),
            }),
        }
        labels = {
            'marks_obtained': _('Marks Obtained'),
            'feedback': _('Feedback'),
        }
        help_texts = {
            'marks_obtained': _('Enter the score out of the total marks.'),
            'feedback': _('Optional, but helpful for student improvement.'),
        }

    def _init_(self, *args, **kwargs):
        super()._init_(*args, **kwargs)
        self.fields['feedback'].required = False

    def clean_marks_obtained(self):
        marks = self.cleaned_data.get('marks_obtained')
        if marks is None:
            return marks
        # Ensure we have an assignment instance
        assignment = self.instance.assignment if self.instance else None
        if assignment:
            if marks > assignment.total_marks:
                raise ValidationError(
                    _(f'Marks cannot exceed the total marks ({assignment.total_marks}).')
                )
            if marks < 0:
                raise ValidationError(_('Marks cannot be negative.'))
        return marks
    
class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'tsc_number']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'tsc_number': forms.TextInput(attrs={'class': 'form-control'}),
        }