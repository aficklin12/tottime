from datetime import date, timedelta
from decimal import Decimal
from django_q.tasks import async_task
from .models import SubUser, WeeklyTuition, TuitionPlan

def process_weekly_tuition():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())  # Monday of this week
    end_of_week = start_of_week + timedelta(days=6)  # Sunday of this week

    # Loop over all active tuition plans
    for tuition_plan in TuitionPlan.objects.filter(is_active=True):
        subuser = tuition_plan.subuser

        # Check if a WeeklyTuition entry already exists for this week and has been charged
        weekly_tuition = WeeklyTuition.objects.filter(
            subuser=subuser,
            start_date=start_of_week,
            end_date=end_of_week
        ).first()

        if weekly_tuition:
            if weekly_tuition.has_been_charged:
                # Skip processing if already charged for this week
                continue
        else:
            # Create a new WeeklyTuition entry if it doesn't exist
            weekly_tuition = WeeklyTuition.objects.create(
                subuser=subuser,
                start_date=start_of_week,
                end_date=end_of_week,
                amount=tuition_plan.weekly_amount,
                amount_paid=Decimal('0.00'),
                status='pending',
                has_been_charged=False
            )

        # Process the tuition charge only if it hasn't been charged yet
        if not weekly_tuition.has_been_charged:
            if subuser.balance >= weekly_tuition.amount:
                # Subuser has enough balance to cover the tuition
                weekly_tuition.amount_paid = weekly_tuition.amount
                weekly_tuition.status = 'paid'
                subuser.balance -= weekly_tuition.amount  # Deduct the full amount from balance
            else:
                # Subuser does not have enough balance, partial payment
                weekly_tuition.amount_paid = max(Decimal('0.00'), subuser.balance)  # Ensure amount_paid is not negative
                weekly_tuition.status = 'partially_paid'
                subuser.balance -= weekly_tuition.amount  # Allow balance to go negative

            weekly_tuition.has_been_charged = True
            weekly_tuition.save()

            # Update SubUser balance after tuition processing
            subuser.save()

    return f"Weekly tuition processed for week starting {start_of_week}"

# To run the task with Django Q
def schedule_weekly_tuition():
    async_task('tottimeapp.tasks.process_weekly_tuition')
