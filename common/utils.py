import os
import mimetypes
from typing import Optional, List
from django.core.files.base import File
from django.conf import settings

try:
    from storages.backends.s3boto3 import S3Boto3Storage
except ImportError:
    S3Boto3Storage = None


# ============================================================================
# FILE & STORAGE UTILITIES
# ============================================================================

def get_presigned_url(file_field, expiration: int = 900) -> Optional[str]:
    """
    Generate a presigned URL for a file stored in S3.

    Args:
        file_field: The file field object (e.g., lesson.video_file).
        expiration: URL expiration time in seconds (default: 15 minutes).

    Returns:
        str: Presigned URL, or None if file_field is empty.

    Usage:
        url = get_presigned_url(lesson.video_file)
    """
    if not file_field:
        return None

    # For S3 storage, generate a presigned URL
    if settings.DEFAULT_FILE_STORAGE == 'storages.backends.s3boto3.S3Boto3Storage':
        if S3Boto3Storage is None:
            raise ImportError("django-storages is not installed")
        storage = S3Boto3Storage()
        return storage.url(file_field.name)

    # For local storage, return the regular URL
    return file_field.url


def validate_file_extension(file_obj: File, allowed_extensions: List[str]) -> bool:
    """
    Validate that the uploaded file has an allowed extension.

    Args:
        file_obj: The uploaded file object.
        allowed_extensions: List of allowed file extensions (e.g., ['.mp4', '.pdf']).

    Returns:
        bool: True if extension is allowed, False otherwise.

    Usage:
        if validate_file_extension(video_file, ['.mp4', '.webm']):
            # Process the file
    """
    if not file_obj or not file_obj.name:
        return False

    ext = os.path.splitext(file_obj.name)[1].lower()
    return ext in allowed_extensions


def get_file_size(file_obj: File) -> str:
    """
    Return the file size in a human_readable format.

    Args:
        file_obj: The file object.

    Returns:
        str: Human_readable file size (e.g., "2.4 MB", "150 KB").

    Usage:
        size = get_file_size(lesson.video_file)  # "15.8 MB"
    """
    if not file_obj:
        return "0 B"

    try:
        size = file_obj.size
    except (AttributeError, TypeError):
        return "0 B"

    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"


def get_mime_type(file_obj: File) -> Optional[str]:
    """
    Get the MIME type of a file.

    Args:
        file_obj: The file object.

    Returns:
        str: MIME type (e.g, 'video/mp4', 'application/pdf').

    Usage:
        mime_type = get_mime_type(lesson.video_file)  # "video/mp4"
    """
    if not file_obj or not file_obj.name:
        return None

    mime_type, _ = mimetypes.guess_type(file_obj.name)
    return mime_type


# ============================================================================
# FORMATTING UTILITIES
# ============================================================================

def format_duration(seconds: Optional[int]) -> str:
    """
    Convert seconds to a human_readable string.

    Args:
        seconds: Duration in seconds.

    Returns:
        str: Formatted duration (e.g., "1h 23m", "45s", "2m 30s").

    Usage:
        {{ lesson.video_duration|format_duration }}
        # Or in Python:
        duration = format_duration(lesson.video_duration)
    """
    if not seconds or seconds <= 0:
        return "0s"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


# ============================================================================
# ADDITIONAL UTILITIES
# ============================================================================

def generate_unique_filename(original_filename: str, prefix: str = '') -> str:
    """
    Generate a unique filename to avoid collisions.

    Args:
        original_filename: The original file name.
        prefix: Optional prefix to add.

    Returns:
        str: Unique filename.

    Usage:
        filename = generate_unique_filename('video.mp4', 'lesson_1')
    """
    from django.utils import timezone
    import uuid

    ext = os.path.splitext(original_filename)[1]
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    base_name = os.path.splitext(original_filename)[0]

    if prefix:
        return f"{prefix}{timestamp}{unique_id}{ext}"
    return f"{base_name}{timestamp}{unique_id}{ext}"


def validate_file_size(file_obj: File, max_size_mb: int = 500) -> bool:
    """
    Validate that the file size is within the limit.

    Args:
        file_obj: The file object.
        max_size_mb: Maximum file size in MB (default: 500).

    Returns:
        bool: True if file size is within the limit, False otherwise.

    Usage:
        if not validate_file_size(video_file, 100):
            raise ValidationError("File size exceeds 100MB limit.")
    """
    if not file_obj:
        return False

    try:
        size_mb = file_obj.size / (1024 * 1024)
        return size_mb <= max_size_mb
    except (AttributeError, TypeError):
        return False


def slugify(text: str) -> str:
    """
    Slugify a string for use in URLs.

    Args:
        text: The text to slugify.

    Returns:
        str: Slugified text.

    Usage:
        slug = slugify("My Lesson Title")  # "my-lesson-title"
    """
    from django.utils.text import slugify as django_slugify
    return django_slugify(text)