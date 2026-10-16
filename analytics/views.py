from datetime import datetime, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Avg, Sum, F, Count, Q
from django.utils import timezone

from common.mixins import AdminRequiredMixin, TeacherRequiredMixin, ParentRequiredMixin
from batches.models import Batch, Enrollment
from accounts.models import User
from content.models import Lesson, LessonProgress, LessonQuestion
from assignments.models import Submission
from .models import DailyAttendanceSnapshot, StudentProgressSnapshot


# ============================================================================
# ADMIN DASHBOARD
# ============================================================================

class AdminDashboardView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Admin dashboard with global stats, live classes, and daily records."""
    template_name = 'analytics/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # ---------- Basic stats ----------
        context['total_teachers'] = User.objects.filter(role='teacher', is_active=True).count()
        context['total_students'] = User.objects.filter(role='student', is_active=True).count()
        context['total_batches'] = Batch.objects.filter(is_active=True).count()
        context['total_lessons'] = Lesson.objects.count()
        context['total_live_classes'] = Lesson.objects.filter(lesson_type='live').count()

        # ---------- Average attendance (last 7 days) ----------
        week_ago = timezone.now().date() - timedelta(days=7)
        recent_snapshots = DailyAttendanceSnapshot.objects.filter(date__gte=week_ago)

        if recent_snapshots.exists():
            avg_att = recent_snapshots.aggregate(avg=Avg('attendance_percentage'))['avg'] or 0
            context['avg_attendance'] = round(avg_att, 1)
        else:
            lessons_last_7d = Lesson.objects.filter(created_at__date__gte=week_ago)
            total_enrolled = Enrollment.objects.filter(
                batch_lessons_in=lessons_last_7d,
                is_active=True
            ).values('student').distinct().count()
            total_attended = LessonProgress.objects.filter(
                lesson__in=lessons_last_7d,
                is_completed=True
            ).values('student').distinct().count()
            context['avg_attendance'] = (
                round((total_attended / total_enrolled) * 100, 1)
                if total_enrolled > 0 else 0
            )

        # ================================================================
        # LIVE CLASSES SECTION
        # ================================================================

        # ---------- 1. Live classes happening right now ----------
        live_now_lessons = Lesson.objects.filter(
            lesson_type='live',
            live_start__lte=timezone.now(),
            live_end__gte=timezone.now(),
        ).select_related('batch', 'batch__teacher').order_by('-live_start')

        live_now_data = []
        for lesson in live_now_lessons:
            live_now_data.append({
                'lesson': lesson,
                'batch': lesson.batch,
                'teacher': lesson.batch.teacher,
                'attended': lesson.live_attended_count,
                'enrolled': lesson.live_enrolled_count,
                'rate': lesson.live_attendance_rate,
            })
        context['live_now_classes'] = live_now_data

        # ---------- 2. Recent live classes (last 30 days) ----------
        recent_live = Lesson.objects.filter(
            lesson_type='live',
            live_start__lte=timezone.now(),
            live_start__gte=timezone.now() - timedelta(days=30),
        ).select_related('batch', 'batch__teacher').order_by('-live_start')[:15]

        live_attendance = []
        for lesson in recent_live:
            live_attendance.append({
                'lesson': lesson,
                'batch': lesson.batch,
                'teacher': lesson.batch.teacher,
                'attended': lesson.live_attended_count,
                'enrolled': lesson.live_enrolled_count,
                'rate': lesson.live_attendance_rate,
                'has_ended': lesson.has_ended,
            })
        context['live_attendance'] = live_attendance

        # ---------- 3. Upcoming live classes ----------
        upcoming_live = Lesson.objects.filter(
            lesson_type='live',
            live_start__gt=timezone.now(),
        ).select_related('batch', 'batch__teacher').order_by('live_start')[:5]

        context['upcoming_live_classes'] = [
            {
                'lesson': l,
                'batch': l.batch,
                'teacher': l.batch.teacher,
                'starts_in': l.starts_in_minutes,
            }
            for l in upcoming_live
        ]

        # ================================================================
        # EXISTING SECTIONS
        # ================================================================

        # ---------- Top 5 batches ----------
        top_batches = DailyAttendanceSnapshot.objects.filter(
            date__gte=timezone.now().date() - timedelta(days=30)
        ).values(
            batch_name=F('batch__name'),
            batch_pk=F('batch__id'),
        ).annotate(
            avg_attendance=Avg('attendance_percentage')
        ).order_by('-avg_attendance')[:5]
        context['top_batches'] = top_batches

        # ---------- Recent lessons ----------
        recent_lessons = Lesson.objects.filter(
            lesson_type='recorded',
            created_at__gte=timezone.now() - timedelta(days=30)
        )[:10]
        lesson_data = []
        for lesson in recent_lessons:
            total_enrolled = lesson.batch.enrollments.filter(is_active=True).count()
            attended = LessonProgress.objects.filter(lesson=lesson, is_completed=True).count()
            rate = (attended / total_enrolled * 100) if total_enrolled else 0
            lesson_data.append({
                'title': lesson.title,
                'batch': lesson.batch.name,
                'teacher': lesson.batch.teacher.get_full_name(),
                'attendance_rate': round(rate, 1),
            })
        context['recent_lessons'] = lesson_data

        # ---------- Weekly chart ----------
        context['chart_data'] = self._get_admin_chart_data()
        context['chart_title'] = 'Weekly Attendance (All Batches)'

        # ---------- Daily attendance record ----------
        today = timezone.now().date()
        selected_date_str = self.request.GET.get('date', today.strftime('%Y-%m-%d'))
        selected_batch = self.request.GET.get('batch')

        try:
            filter_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            filter_date = today

        progress_qs = LessonProgress.objects.filter(
            last_activity__date=filter_date
        ).select_related(
            'student',
            'lesson',
            'lesson__batch',
            'lesson__batch__teacher',
        )

        if selected_batch:
            progress_qs = progress_qs.filter(lesson__batch_id=selected_batch)

        attendance_records = []
        for progress in progress_qs:
            attendance_records.append({
                'date': filter_date,
                'batch': progress.lesson.batch,
                'student': progress.student,
                'lesson': progress.lesson,
                'lesson_type': progress.lesson.lesson_type,
                'watch_percentage': float(progress.watch_percentage or 0),
                'is_completed': progress.is_completed,
                'total_watch_seconds': progress.total_watch_seconds,
            })

        attendance_records.sort(
            key=lambda r: (r['batch'].name, r['student'].get_full_name() or r['student'].username)
        )

        all_batches = Batch.objects.filter(is_active=True).order_by('name')
        total_students_today = len(set(r['student'].id for r in attendance_records))
        total_completed = sum(1 for r in attendance_records if r['is_completed'])

        context['attendance_records'] = attendance_records
        context['selected_date'] = filter_date
        context['selected_batch'] = selected_batch
        context['all_batches'] = all_batches
        context['total_students_today'] = total_students_today
        context['total_completed'] = total_completed
        context['attendance_rate'] = (
            round((total_completed / total_students_today) * 100, 1)
            if total_students_today > 0 else 0
        )

        return context

    def _get_admin_chart_data(self):
        today = timezone.now().date()
        days, attended, enrolled = [], [], []

        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            days.append(date.strftime('%a'))

            snapshots = DailyAttendanceSnapshot.objects.filter(date=date)
            if snapshots.exists():
                total_enrolled = snapshots.aggregate(s=Sum('total_enrolled'))['s'] or 0
                total_attended = snapshots.aggregate(s=Sum('attended_count'))['s'] or 0
            else:
                # FIXED: First, find which lessons actually happened on this day
                lessons_that_day = Lesson.objects.filter(created_at__date=date)
                
                # FIXED: Count only distinct students enrolled in batches that had lessons that day
                total_enrolled = Enrollment.objects.filter(
                    batch__lessons__in=lessons_that_day,
                    is_active=True
                ).values('student').distinct().count()
                
                # FIXED: Count only distinct students who completed those specific lessons
                total_attended = LessonProgress.objects.filter(
                    lesson__in=lessons_that_day,
                    last_activity__date=date,
                    is_completed=True
                ).values('student').distinct().count()

            enrolled.append(total_enrolled)
            attended.append(total_attended)

        return {
            'labels': days,
            'datasets': [
                {
                    'label': 'Attended',
                    'data': attended,
                    'backgroundColor': 'rgba(40, 167, 69, 0.6)',
                    'borderColor': 'rgba(40, 167, 69, 1)',
                    'borderWidth': 1,
                },
                {
                    'label': 'Total Enrolled',
                    'data': enrolled,
                    'backgroundColor': 'rgba(255, 193, 7, 0.3)',
                    'borderColor': 'rgba(255, 193, 7, 1)',
                    'borderWidth': 1,
                    'borderDash': [5, 5],
                    'fill': False,
                },
            ]
        }

# ============================================================================
# TEACHER ANALYTICS
# ============================================================================

class TeacherAnalyticsView(LoginRequiredMixin, TeacherRequiredMixin, TemplateView):
    """Teacher dashboard with batch stats, live classes, and pending submissions."""
    template_name = 'analytics/teacher_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        teacher = self.request.user
        batches = Batch.objects.filter(teacher=teacher, is_active=True)
        context['batches'] = batches

        # ---------- Unanswered questions ----------
        context['unanswered_questions'] = LessonQuestion.objects.filter(
            lesson__batch__in=batches,
            replies__isnull=True
        ).select_related('student', 'lesson', 'lesson__batch').order_by('-created_at')[:10]

        # ---------- Overall stats ----------
        total_students = Enrollment.objects.filter(
            batch__in=batches, is_active=True
        ).count()
        context['total_students'] = total_students
        context['total_batches'] = batches.count()
        context['total_lessons'] = Lesson.objects.filter(batch__in=batches).count()

        # ---------- Pending submissions ----------
        context['total_pending_submissions'] = Submission.objects.filter(
            assignment__batch__in=batches,
            marks_obtained__isnull=True
        ).count()

        # ================================================================
        # LIVE CLASSES FOR THIS TEACHER
        # ================================================================

        # ---------- Live classes happening right now ----------
        live_now = Lesson.objects.filter(
            batch__in=batches,
            lesson_type='live',
            live_start__lte=timezone.now(),
            live_end__gte=timezone.now(),
        ).select_related('batch').order_by('-live_start')

        live_now_data = []
        for lesson in live_now:
            live_now_data.append({
                'lesson': lesson,
                'batch': lesson.batch,
                'attended': lesson.live_attended_count,
                'enrolled': lesson.live_enrolled_count,
                'rate': lesson.live_attendance_rate,
            })
        context['live_now_classes'] = live_now_data

        # ---------- Recent live classes (last 30 days) ----------
        recent_live = Lesson.objects.filter(
            batch__in=batches,
            lesson_type='live',
            live_start__lte=timezone.now(),
            live_start__gte=timezone.now() - timedelta(days=30),
        ).select_related('batch').order_by('-live_start')[:15]

        live_attendance = []
        for lesson in recent_live:
            live_attendance.append({
                'lesson': lesson,
                'batch': lesson.batch,
                'attended': lesson.live_attended_count,
                'enrolled': lesson.live_enrolled_count,
                'rate': lesson.live_attendance_rate,
                'has_ended': lesson.has_ended,
            })
        context['live_attendance'] = live_attendance

        # ---------- Upcoming live classes ----------
        upcoming_live = Lesson.objects.filter(
            batch__in=batches,
            lesson_type='live',
            live_start__gt=timezone.now(),
        ).select_related('batch').order_by('live_start')[:5]

        context['upcoming_live_classes'] = [
            {
                'lesson': l,
                'batch': l.batch,
                'starts_in': l.starts_in_minutes,
            }
            for l in upcoming_live
        ]

        # ---------- Average attendance (recorded lessons, last 30 days) ----------
        recent_lessons = Lesson.objects.filter(
            batch__in=batches,
            lesson_type='recorded',
            created_at__gte=timezone.now() - timedelta(days=30)
        )
        if recent_lessons.exists():
            lesson_rates = []
            for lesson in recent_lessons:
                enrolled = lesson.batch.enrollments.filter(is_active=True).count()
                if enrolled == 0:
                    continue
                attended = LessonProgress.objects.filter(
                    lesson=lesson, is_completed=True
                ).count()
                lesson_rates.append((attended / enrolled) * 100)
            context['avg_attendance'] = (
                round(sum(lesson_rates) / len(lesson_rates), 1)
                if lesson_rates else 0
            )
        else:
            context['avg_attendance'] = 0

        # ---------- Per-batch stats ----------
        batch_stats = []
        for batch in batches:
            enrolled = batch.enrollments.filter(is_active=True).count()
            lessons = batch.lessons.filter(lesson_type='recorded').count()

            completed_records = LessonProgress.objects.filter(
                lesson__in=batch.lessons.filter(lesson_type='recorded'),
                is_completed=True
            ).count()

            total_possible = enrolled * lessons
            progress = (
                round((completed_records / total_possible) * 100, 1)
                if total_possible else 0
            )

            pending_submissions = Submission.objects.filter(
                assignment__batch=batch,
                marks_obtained__isnull=True
            ).count()

            total_submissions = Submission.objects.filter(
                assignment__batch=batch
            ).count()

            # Live count for this batch
            live_count = batch.lessons.filter(lesson_type='live').count()

            batch_stats.append({
                'batch': batch,
                'enrolled': enrolled,
                'lessons': lessons,
                'live_count': live_count,
                'completed': completed_records,
                'total_possible': total_possible,
                'progress': progress,
                'pending_submissions': pending_submissions,
                'total_submissions': total_submissions,
            })
        context['batch_stats'] = batch_stats

        # ---------- Chart ----------
        context['chart_data'] = self._get_attendance_chart_data(batches)
        context['chart_title'] = 'Attendance This Week'

        return context

    def _get_attendance_chart_data(self, batches):
        today = timezone.now().date()
        days, attended, enrolled = [], [], []

        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            days.append(date.strftime('%a'))

            snapshots = DailyAttendanceSnapshot.objects.filter(
                batch__in=batches,
                date=date
            )
            if snapshots.exists():
                total_enrolled = snapshots.aggregate(s=Sum('total_enrolled'))['s'] or 0
                total_attended = snapshots.aggregate(s=Sum('attended_count'))['s'] or 0
            else:
                total_attended = LessonProgress.objects.filter(
                    lesson__batch__in=batches,
                    last_activity__date=date,
                    is_completed=True
                ).values('student').distinct().count()

                total_enrolled = Enrollment.objects.filter(
                    batch__in=batches,
                    is_active=True
                ).count()

            enrolled.append(total_enrolled)
            attended.append(total_attended)

        return {
            'labels': days,
            'datasets': [
                {
                    'label': 'Attended',
                    'data': attended,
                    'backgroundColor': 'rgba(40, 167, 69, 0.6)',
                    'borderColor': 'rgba(40, 167, 69, 1)',
                    'borderWidth': 1,
                },
                {
                    'label': 'Total Enrolled',
                    'data': enrolled,
                    'backgroundColor': 'rgba(255, 193, 7, 0.3)',
                    'borderColor': 'rgba(255, 193, 7, 1)',
                    'borderWidth': 1,
                    'borderDash': [5, 5],
                    'fill': False,
                },
            ]
        }


# ============================================================================
# PARENT ANALYTICS
# ============================================================================

class ParentAnalyticsView(LoginRequiredMixin, ParentRequiredMixin, TemplateView):
    """Parent dashboard showing children's progress."""
    template_name = 'analytics/parent_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        children = self.request.user.children.all()
        context['children'] = children

        child_data = []
        for child in children:
            enrollments = Enrollment.objects.filter(
                student=child, is_active=True
            ).select_related('batch', 'batch__teacher')

            for enrollment in enrollments:
                batch = enrollment.batch

                batch_progress = StudentProgressSnapshot.objects.filter(
                    student=child,
                    batch=batch
                ).order_by('-snapshot_date').first()

                lessons = batch.lessons.all().order_by('order', 'created_at')
                lesson_rows = []
                for lesson in lessons:
                    lp = LessonProgress.objects.filter(
                        student=child,
                        lesson=lesson
                    ).first()

                    lesson_rows.append({
                        'lesson': lesson,
                        'lesson_type': lesson.lesson_type,
                        'watch_percentage': float(lp.watch_percentage) if lp else 0.0,
                        'is_completed': lp.is_completed if lp else False,
                        'total_watch_seconds': lp.total_watch_seconds if lp else 0,
                        'attended_minutes': (
                            round(lp.total_watch_seconds / 60, 1) if lp else 0
                        ),
                    })

                child_data.append({
                    'child': child,
                    'batch': batch,
                    'progress': batch_progress,
                    'lessons': lesson_rows,
                    'total_lessons': len(lesson_rows),
                    'completed_lessons': sum(1 for r in lesson_rows if r['is_completed']),
                })

        context['child_data'] = child_data

        progress_values = [
            d['progress'].completion_percentage
            for d in child_data if d['progress']
        ]
        context['avg_completion'] = (
            round(sum(progress_values) / len(progress_values), 1)
            if progress_values else 0
        )

        return context