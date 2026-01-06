from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def get_base_template(context):
    """
    Returns the correct base template based on context and viewport cookie.
    """
    request = context.get('request')

    # Prefer explicit context flag set by context processor
    use_minimal = bool(context.get('use_minimal_base'))

    # Fallback to cookie if flag missing
    if not use_minimal and request is not None:
        try:
            vw_cookie = request.COOKIES.get('viewport_width')
            vw = int(vw_cookie) if vw_cookie else None
            use_minimal = vw is not None and vw < 1000
        except (TypeError, ValueError):
            pass

    if use_minimal:
        return 'tottimeapp/base_minimal.html'
    if context.get('is_public_view'):
        return 'tottimeapp/base_public.html'
    return 'tottimeapp/base.html'