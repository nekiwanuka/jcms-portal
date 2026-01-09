from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from invoices.models import Invoice
from clients.models import Client


class Command(BaseCommand):
    help = 'Send due date reminders for overdue invoices'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=3,
            help='Send reminders for invoices due in this many days',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )

    def handle(self, *args, **options):
        days_ahead = options['days_ahead']
        dry_run = options['dry_run']

        # Calculate the date range for reminders
        today = timezone.now().date()
        reminder_date = today + timezone.timedelta(days=days_ahead)

        # Find invoices that are due soon and not fully paid
        overdue_invoices = Invoice.objects.filter(
            due_at__date__lte=reminder_date,
            status__in=[Invoice.Status.SENT, Invoice.Status.PARTIALLY_PAID]
        ).select_related('client')

        self.stdout.write(f"Found {overdue_invoices.count()} invoices due by {reminder_date}")

        emails_sent = 0
        for invoice in overdue_invoices:
            if dry_run:
                self.stdout.write(f"Would send reminder for Invoice {invoice.number} to {invoice.client.email}")
            else:
                try:
                    self.send_reminder_email(invoice)
                    emails_sent += 1
                    self.stdout.write(f"Sent reminder for Invoice {invoice.number}")
                except Exception as e:
                    self.stderr.write(f"Failed to send reminder for Invoice {invoice.number}: {e}")

        if not dry_run:
            self.stdout.write(f"Successfully sent {emails_sent} reminder emails")
        else:
            self.stdout.write(f"Would send {overdue_invoices.count()} reminder emails")


    def send_reminder_email(self, invoice):
        """Send a due date reminder email for an invoice."""
        subject = f"Payment Reminder - Invoice {invoice.number}"

        context = {
            'invoice': invoice,
            'client': invoice.client,
            'company_name': 'Jambas Imaging (U) Ltd',
            'due_date': invoice.due_at.date() if invoice.due_at else None,
            'outstanding_amount': invoice.outstanding_balance(),
        }

        # Render email templates
        html_message = render_to_string('emails/invoice_reminder.html', context)
        text_message = render_to_string('emails/invoice_reminder.txt', context)

        send_mail(
            subject=subject,
            message=text_message,
            html_message=html_message,
            from_email='info@jambasimaging.com',
            recipient_list=[invoice.client.email],
            fail_silently=False,
        )