from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Get an item from a dictionary by key.
    Usage: {{ dict|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(str(key))