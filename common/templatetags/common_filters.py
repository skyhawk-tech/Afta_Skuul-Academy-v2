from django import template
from common.utils import format_duration, get_file_size

register = template.Library()

@register.filter
def format_duration_filter(seconds):
    return format_duration(seconds)

@register.filter
def file_size(file_obj):
    return get_file_size(file_obj)