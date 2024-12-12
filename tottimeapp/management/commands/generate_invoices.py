from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
from tottimeapp.models import Payment
from django.db.models import Max, Q

class Command(BaseCommand):
    help = 'Generate recurring invoices based on frequency for each student'

    def handle(self, *args, **kwargs):
        today = now().date()

        # Fetch the latest payment for each student and frequency
        latest_payments = (
            Payment.objects.values('student_id', 'frequency')
            .annotate(latest_id=Max('id'))
        )

        for entry in latest_payments:
            # Get the latest payment instance for this student and frequency
            payment = Payment.objects.get(id=entry['latest_id'])

            # Skip if the end_date is before today
            if payment.end_date and payment.end_date < today:
                continue

            # Determine the next invoice date
            if not payment.next_invoice_date:
                next_invoice_date = today
            else:
                next_invoice_date = payment.next_invoice_date

            # Calculate the due date based on the frequency
            if payment.frequency == 'weekly':
                due_date = next_invoice_date + timedelta(weeks=1)
                next_invoice_date += timedelta(weeks=1)
            elif payment.frequency == 'monthly':
                due_date = next_invoice_date + timedelta(days=30)
                next_invoice_date += timedelta(days=30)
            elif payment.frequency == 'yearly':
                due_date = next_invoice_date + timedelta(days=365)
                next_invoice_date += timedelta(days=365)

            # Check if an invoice already exists for this period
            existing_invoice = Payment.objects.filter(
                student_id=payment.student_id,
                frequency=payment.frequency,
                due_date=due_date,
            ).exists()

            if existing_invoice:
                self.stdout.write(
                    f"Skipping: Invoice for student {payment.student_id} "
                    f"and frequency {payment.frequency} already exists for {due_date}."
                )
                continue

            # Create the new invoice
            new_payment = Payment.objects.create(
                subuser=payment.subuser,
                student=payment.student,
                amount=payment.amount,
                frequency=payment.frequency,
                start_date=today,
                due_date=due_date,
                notes=payment.notes,
                balance=payment.amount,
                status='Pending',  # Explicitly set the status
                payment_method=payment.payment_method,
            )

            # Update the next invoice date for the current payment
            payment.next_invoice_date = next_invoice_date
            payment.save()

            # Log success
            self.stdout.write(
                self.style.SUCCESS(
                    f"Invoice created for student {payment.student_id} "
                    f"with due date {due_date}."
                )
            )

        self.stdout.write(self.style.SUCCESS("Recurring invoices processed successfully."))
