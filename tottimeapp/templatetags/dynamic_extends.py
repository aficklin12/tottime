from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def get_base_template(context):
    """
    Determine which base template to use based on the context.
    If is_public_view is True, returns the public base template.
    Otherwise returns the standard base template.
    
    Usage in templates:
        {% load dynamic_extends %}
        {% extends get_base_template %}
    """
    if context.get('is_public_view'):
        return 'tottimeapp/base_public.html'
    else:
        return 'tottimeapp/base.html'