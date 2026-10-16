from typing import Dict, Any
from django.http import HttpRequest
from django.conf import settings

from batches.models import Batch


def common_context(request: HttpRequest) -> Dict[str, Any]:
    """
    Add common variables to every template.
    """
    context: Dict[str, Any] = {}

    if not request.user.is_authenticated:
        return context

    user = request.user
    role = user.role

    if role == 'teacher':
        context['batch_count'] = Batch.objects.filter(teacher=user, is_active=True).count()
        context['active_batch_ids'] = list(
            Batch.objects.filter(teacher=user, is_active=True).values_list('id', flat=True)
        )

    elif role == 'student':
        context['enrolled_count'] = user.enrollments.filter(is_active=True).count()
        context['enrolled_batch_ids'] = list(
            user.enrollments.filter(is_active=True).values_list('batch_id', flat=True)
        )
        context['ungraded_submissions_count'] = user.submissions.filter(
            marks_obtained__isnull=True
        ).count()

    elif role == 'parent':
        context['children_count'] = user.children.count()
        context['child_ids'] = list(user.children.values_list('id', flat=True))
        # ✅ CORRECTED LINE – use double underscores
        context['children_enrolled_batches'] = (
            Batch.objects.filter(
                enrollments__student__in=user.children.all(),
                enrollments__is_active=True
            ).distinct().count()
        )

    # Global variables
    context['user_role'] = role
    context['user_full_name'] = user.get_full_name() or user.username
    context['user_display_name'] = user.get_full_name() or user.username

    return context