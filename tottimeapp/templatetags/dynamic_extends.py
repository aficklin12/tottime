from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def get_base_template(context):
    
    """
    Returns the correct base template based on context.
    """
    if context.get('use_minimal_base'):
        return 'tottimeapp/base_minimal.html'
    if context.get('is_public_view'):
        return 'tottimeapp/base_public.html'
    return 'tottimeapp/base.html'