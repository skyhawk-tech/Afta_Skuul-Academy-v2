from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Lesson, LessonQuestion, LessonReply


# ============================================================================
# LESSON FORM
# ============================================================================

class LessonForm(forms.ModelForm):
    """
    Form for creating and editing lessons (recorded video OR live class).
    """

    class Meta:
        model = Lesson
        fields = [
            'title', 'description', 'chapter', 'part_number',
            'lesson_type',
            'video_file', 'video_url', 'video_duration',
            'notes_file', 'order', 'required_watch_percentage',
            'release_date', 'live_start', 'live_end',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter lesson title',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe the lesson content...',
            }),
            'chapter': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Chapter 1 – Introduction',
            }),
            'part_number': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'step': 1,
            }),
            'lesson_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_lesson_type',
            }),
            'video_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/*',
            }),
            'video_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://www.youtube.com/watch?v=...',
            }),
            'video_duration': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'step': 1,
                'placeholder': 'e.g., 900 = 15 minutes',
            }),
            'notes_file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt',
            }),
            'order': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'step': 1,
                'placeholder': '0',
            }),
            'required_watch_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 100,
                'step': 1,
                'placeholder': '80',
            }),
            'release_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'live_start': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'live_end': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
        }
        labels = {
            'title': _('Lesson Title'),
            'description': _('Description'),
            'chapter': _('Chapter (optional)'),
            'part_number': _('Part Number'),
            'lesson_type': _('Lesson Type'),
            'video_file': _('Video File'),
            'video_url': _('Video URL (Optional)'),
            'video_duration': _('Duration (seconds)'),
            'notes_file': _('Notes (PDF/Word)'),
            'order': _('Display Order'),
            'required_watch_percentage': _('Required Watch Percentage'),
            'release_date': _('Release Date'),
            'live_start': _('Class Starts'),
            'live_end': _('Class Ends'),
        }
        help_texts = {
            'chapter': _('Group split videos by chapter.'),
            'lesson_type': _('Choose Live Class for scheduled video calls.'),
            'video_file': _('Upload MP4, WebM, or OGG (max 500 MB).'),
            'video_url': _('If you have a hosted video, provide the URL instead.'),
            'video_duration': _('Video length in seconds (e.g., 900 = 15 minutes).'),
            'notes_file': _('Upload supplementary notes (PDF, Word, or TXT).'),
            'order': _('Lessons with lower numbers appear first.'),
            'required_watch_percentage': _('Percentage of video that must be watched to mark as completed.'),
            'release_date': _('Leave blank to publish immediately.'),
            'live_start': _('When the live class will begin.'),
            'live_end': _('When the live class will end.'),
        }

    # ========================================================================
    # ✅ SINGLE _init_ (double underscores, NOT init)
    # ========================================================================
    def _init_(self, *args, **kwargs):
        super()._init_(*args, **kwargs)

        # Mark required fields
        self.fields['title'].required = True
        self.fields['lesson_type'].required = True

        # Pre-fill live class times for NEW lessons only
        if not self.instance.pk:
            now = timezone.now()

            # Round up to the next 5-minute mark
            minutes = (now.minute // 5 + 1) * 5
            if minutes >= 60:
                now = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            else:
                now = now.replace(minute=minutes, second=0, microsecond=0)

            self.fields['live_start'].initial = now
            self.fields['live_end'].initial = now + timedelta(hours=1)

    # ========================================================================
    # CLEAN METHODS
    # ========================================================================
    def clean(self):
        cleaned_data = super().clean()
        lesson_type = cleaned_data.get('lesson_type')
        video_file = cleaned_data.get('video_file')
        video_url = cleaned_data.get('video_url')
        live_start = cleaned_data.get('live_start')
        live_end = cleaned_data.get('live_end')

        if lesson_type == 'recorded':
            if not video_file and not video_url:
                raise ValidationError(
                    _('Recorded lessons must have either a video file or a video URL.')
                )

        if lesson_type == 'live':
            if not live_start or not live_end:
                raise ValidationError(
                    _('Live lessons must have a start and end time.')
                )
            if live_end <= live_start:
                raise ValidationError({
                    'live_end': _('End time must be after start time.')
                })

        return cleaned_data

    def clean_video_file(self):
        video = self.cleaned_data.get('video_file')
        if not video:
            return video
        ext = video.name.split('.')[-1].lower()
        allowed = ['mp4', 'webm', 'ogg', 'mov', 'avi']
        if ext not in allowed:
            raise ValidationError(
                _(f'Unsupported file type. Allowed: {", ".join(allowed)}.')
            )
        max_size = 500 * 1024 * 1024
        if video.size > max_size:
            raise ValidationError(
                _(f'File too large. Maximum size is 500 MB '
                  f'(your file: {video.size / (1024*1024):.1f} MB).')
            )
        return video

    def clean_notes_file(self):
        notes = self.cleaned_data.get('notes_file')
        if not notes:
            return notes
        ext = notes.name.split('.')[-1].lower()
        allowed = ['pdf', 'doc', 'docx', 'txt', 'rtf']
        if ext not in allowed:
            raise ValidationError(
                _(f'Unsupported file type for notes. Allowed: {", ".join(allowed)}.')
            )
        if notes.size > 20 * 1024 * 1024:
            raise ValidationError(_('Notes file too large. Maximum size is 20 MB.'))
        return notes

    def clean_release_date(self):
        release_date = self.cleaned_data.get('release_date')
        if release_date and release_date < timezone.now():
            raise ValidationError(_('Release date cannot be in the past.'))
        return release_date

    def clean_video_duration(self):
        duration = self.cleaned_data.get('video_duration')
        if duration is not None and duration < 0:
            raise ValidationError(_('Duration cannot be negative.'))
        return duration

    def clean_order(self):
        order = self.cleaned_data.get('order')
        if order is not None and order < 0:
            raise ValidationError(_('Order cannot be negative.'))
        return order

    def clean_required_watch_percentage(self):
        percentage = self.cleaned_data.get('required_watch_percentage')
        if percentage is not None and (percentage < 0 or percentage > 100):
            raise ValidationError(_('Percentage must be between 0 and 100.'))
        return percentage


# ============================================================================
# LESSON QUESTION FORM
# ============================================================================

class LessonQuestionForm(forms.ModelForm):
    """Form for students to ask a question on a lesson."""

    class Meta:
        model = LessonQuestion
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Ask your question about this lesson…',
            }),
        }
        labels = {'body': ''}


# ============================================================================
# LESSON REPLY FORM
# ============================================================================

class LessonReplyForm(forms.ModelForm):
    """Form to reply to a lesson question (teacher or student)."""

    class Meta:
        model = LessonReply
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Write your reply…',
            }),
        }
        labels = {'body': ''}