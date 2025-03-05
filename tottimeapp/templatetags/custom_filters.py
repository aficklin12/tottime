from django import template
from tottimeapp.models import AttendanceRecord
from datetime import date

register = template.Library()

@register.filter
def current_attendance_count(classroom, user):
    """
    Counts students who have signed in but have NOT signed out for the given classroom.
    """
    today = date.today()
    return AttendanceRecord.objects.filter(
        classroom_override=classroom,
        sign_in_time__date=today,
        sign_out_time__isnull=True,
        user=user
    ).count()