from rest_framework import permissions
from batches.models import Enrollment

class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'

class IsTeacherOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['admin', 'teacher']

class IsTeacherOfBatch(permissions.BasePermission):
    """
    Object‑level permission: user must be the teacher of the batch.
    Works for Batch, Lesson, Assignment, Enrollment.
    """
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True
        if request.user.role == 'teacher':
            batch = None
            if hasattr(obj, 'batch'):
                batch = obj.batch
            elif hasattr(obj, 'teacher'):
                batch = obj
            elif hasattr(obj, 'lesson'):
                batch = obj.lesson.batch
            elif hasattr(obj, 'assignment'):
                batch = obj.assignment.batch
            else:
                return False
            return batch.teacher == request.user
        return False

class IsEnrolledStudent(permissions.BasePermission):
    """
    Object‑level permission: student must be enrolled in the batch.
    Works for Lesson, Assignment, Batch.
    """
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True
        if request.user.role == 'student':
            batch = None
            if hasattr(obj, 'batch'):
                batch = obj.batch
            elif hasattr(obj, 'lesson'):
                batch = obj.lesson.batch
            elif hasattr(obj, 'assignment'):
                batch = obj.assignment.batch
            else:
                return False
            return Enrollment.objects.filter(student=request.user, batch=batch, is_active=True).exists()
        return False

class IsParentOfStudent(permissions.BasePermission):
    """
    Object‑level permission: parent must be linked to the student.
    Works for User (student) or Submission.
    """
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True
        if request.user.role == 'parent':
            student = None
            if hasattr(obj, 'student'):
                student = obj.student
            elif hasattr(obj, 'student_id'):
                student = obj.student
            else:
                student = obj  # assume the object itself is a User
            return student in request.user.children.all()
        return False