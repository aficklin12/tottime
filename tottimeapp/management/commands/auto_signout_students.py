from django.core.management.base import BaseCommand
from django.utils import timezone
from tottimeapp.models import AttendanceRecord

class Command(BaseCommand):
    help = 'Automatically signs out students who forgot to sign out by 11:59pm'

    def handle(self, *args, **kwargs):
        now = timezone.localtime()
        # Get yesterday's date
        yesterday = now.date() - timezone.timedelta(days=1)
        # Set sign_out_time to 23:59:59 for records from yesterday with no sign_out_time
        records = AttendanceRecord.objects.filter(
            sign_in_time__date=yesterday,
            sign_out_time__isnull=True
        )
        count = records.update(sign_out_time=timezone.make_aware(
            timezone.datetime.combine(yesterday, timezone.datetime.max.time().replace(hour=23, minute=59, second=59))
        ))
        self.stdout.write(self.style.SUCCESS(f'Signed out {count} students for {yesterday}'))