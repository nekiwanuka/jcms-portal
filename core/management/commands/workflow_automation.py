from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from invoices.models import Invoice
from appointments.models import Appointment
from documents.models import Document
from django.template.loader import render_to_string


class Command(BaseCommand):
    help = 'Run automated workflow tasks including reminders and status updates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send-reminders',
            action='store_true',
            help='Send automated reminders for due items',
        )
        parser.add_argument(
            '--update-statuses',
            action='store_true',
            help='Update statuses based on dates and conditions',
        )
        parser.add_argument(
            '--process-workflows',
            action='store_true',
            help='Process automated workflow triggers',
        )

    def handle(self, *args, **options):
        send_reminders = options['send_reminders']
        update_statuses = options['update_statuses']
        process_workflows = options['process_workflows']

        if not any([send_reminders, update_statuses, process_workflows]):
            # Run all by default
            send_reminders = update_statuses = process_workflows = True

        if send_reminders:
            self.send_invoice_reminders()
            self.send_appointment_reminders()
            self.send_document_expiry_reminders()

        if update_statuses:
            self.update_overdue_invoices()
            self.update_expired_documents()
            self.update_completed_appointments()

        if process_workflows:
            self.process_automated_workflows()

        self.stdout.write(
            self.style.SUCCESS('Workflow automation completed successfully')
        )

    def send_invoice_reminders(self):
        """Send reminders for invoices due within 7 days."""
        due_soon = timezone.now().date() + timezone.timedelta(days=7)
        due_invoices = Invoice.objects.filter(
            due_at__lte=due_soon,
            due_at__gte=timezone.now().date(),
            status__in=['issued', 'paid']  # Adjust status values based on actual model
        ).select_related('client')

        for invoice in due_invoices:
            days_until_due = (invoice.due_at - timezone.now().date()).days
            if days_until_due <= 3:  # Urgent reminders
                self.send_urgent_invoice_reminder(invoice, days_until_due)
            elif days_until_due <= 7:  # Regular reminders
                self.send_regular_invoice_reminder(invoice, days_until_due)

    def send_appointment_reminders(self):
        """Send reminders for upcoming appointments."""
        tomorrow = timezone.now().date() + timezone.timedelta(days=1)
        upcoming_appointments = Appointment.objects.filter(
            scheduled_for__date=tomorrow,
            status='confirmed'  # Use confirmed instead of scheduled
        ).select_related('client')

        for appointment in upcoming_appointments:
            self.send_appointment_reminder(appointment)

    def send_document_expiry_reminders(self):
        """Send reminders for documents expiring soon."""
        expiry_threshold = timezone.now().date() + timezone.timedelta(days=30)
        expiring_documents = Document.objects.filter(
            expiry_date__lte=expiry_threshold,
            expiry_date__gte=timezone.now().date(),
            verification_status='approved'
        ).select_related('client', 'uploaded_by')

        for document in expiring_documents:
            days_until_expiry = (document.expiry_date - timezone.now().date()).days
            self.send_document_expiry_reminder(document, days_until_expiry)

    def update_overdue_invoices(self):
        """Mark invoices as overdue when due date has passed."""
        overdue_invoices = Invoice.objects.filter(
            due_at__lt=timezone.now().date(),
            status__in=['issued', 'paid']  # Only check issued invoices that aren't fully paid
        )

        updated_count = 0
        for invoice in overdue_invoices:
            if invoice.status != 'overdue':
                invoice.status = 'overdue'
                invoice.save()
                updated_count += 1
                self.stdout.write(f'Marked invoice {invoice.invoice_number} as overdue')

        self.stdout.write(f'Updated {updated_count} invoices to overdue status')

    def update_expired_documents(self):
        """Mark documents as expired when expiry date has passed."""
        expired_documents = Document.objects.filter(
            expiry_date__lt=timezone.now().date(),
            verification_status__in=['approved', 'pending']
        )

        updated_count = 0
        for document in expired_documents:
            if document.verification_status != 'expired':
                document.verification_status = 'expired'
                document.save()
                updated_count += 1
                self.stdout.write(f'Marked document "{document.title}" as expired')

        self.stdout.write(f'Updated {updated_count} documents to expired status')

    def update_completed_appointments(self):
        """Mark past appointments as completed."""
        past_appointments = Appointment.objects.filter(
            scheduled_for__date__lt=timezone.now().date(),
            status='confirmed'
        )

        updated_count = 0
        for appointment in past_appointments:
            appointment.status = 'completed'
            appointment.save()
            updated_count += 1
            self.stdout.write(f'Marked appointment "{appointment.title}" as completed')

        self.stdout.write(f'Updated {updated_count} appointments to completed status')

    def process_automated_workflows(self):
        """Process automated workflow triggers."""
        # Example: Auto-approve documents that don't require approval
        auto_approve_docs = Document.objects.filter(
            approval_workflow='none',
            verification_status='pending'
        )

        approved_count = 0
        for doc in auto_approve_docs:
            doc.verification_status = 'approved'
            doc.save()
            approved_count += 1

        self.stdout.write(f'Auto-approved {approved_count} documents')

        # Example: Escalate pending approvals after 7 days
        seven_days_ago = timezone.now() - timezone.timedelta(days=7)
        pending_long_docs = Document.objects.filter(
            verification_status='pending',
            uploaded_at__lte=seven_days_ago,
            approval_workflow__in=['single', 'multi', 'sequential']
        )

        escalated_count = 0
        for doc in pending_long_docs:
            # Here you could send escalation emails or update priorities
            escalated_count += 1

        self.stdout.write(f'Escalated {escalated_count} long-pending documents')

    def send_urgent_invoice_reminder(self, invoice, days_until_due):
        """Send urgent payment reminder."""
        subject = f'URGENT: Invoice {invoice.invoice_number} Due in {days_until_due} Days'

        context = {
            'invoice': invoice,
            'days_until_due': days_until_due,
            'urgent': True,
        }

        html_message = render_to_string('emails/invoice_urgent_reminder.html', context)
        plain_message = render_to_string('emails/invoice_urgent_reminder.txt', context)

        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                recipient_list=[invoice.client.email],
                html_message=html_message,
                fail_silently=False,
            )
            self.stdout.write(f'Sent urgent reminder for invoice {invoice.invoice_number}')
        except Exception as e:
            self.stderr.write(f'Failed to send urgent reminder for invoice {invoice.invoice_number}: {str(e)}')

    def send_regular_invoice_reminder(self, invoice, days_until_due):
        """Send regular payment reminder."""
        subject = f'Invoice {invoice.invoice_number} Due in {days_until_due} Days'

        context = {
            'invoice': invoice,
            'days_until_due': days_until_due,
            'urgent': False,
        }

        html_message = render_to_string('emails/invoice_reminder.html', context)
        plain_message = render_to_string('emails/invoice_reminder.txt', context)

        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                recipient_list=[invoice.client.email],
                html_message=html_message,
                fail_silently=False,
            )
            self.stdout.write(f'Sent regular reminder for invoice {invoice.invoice_number}')
        except Exception as e:
            self.stderr.write(f'Failed to send regular reminder for invoice {invoice.invoice_number}: {str(e)}')

    def send_appointment_reminder(self, appointment):
        """Send appointment reminder."""
        subject = f'Appointment Reminder: {appointment.title} Tomorrow'

        context = {
            'appointment': appointment,
        }

        html_message = render_to_string('emails/appointment_reminder.html', context)
        plain_message = render_to_string('emails/appointment_reminder.txt', context)

        recipients = []
        if appointment.client and appointment.client.email:
            recipients.append(appointment.client.email)

        if recipients:
            try:
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                    recipient_list=recipients,
                    html_message=html_message,
                    fail_silently=False,
                )
                self.stdout.write(f'Sent appointment reminder for "{appointment.title}"')
            except Exception as e:
                self.stderr.write(f'Failed to send appointment reminder for "{appointment.title}": {str(e)}')

    def send_document_expiry_reminder(self, document, days_until_expiry):
        """Send document expiry reminder."""
        subject = f'Document Expiring Soon: {document.title}'

        context = {
            'document': document,
            'days_until_expiry': days_until_expiry,
        }

        html_message = render_to_string('emails/document_expiring.html', context)
        plain_message = render_to_string('emails/document_expiring.txt', context)

        recipients = []
        if document.uploaded_by and document.uploaded_by.email:
            recipients.append(document.uploaded_by.email)

        if recipients:
            try:
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                    recipient_list=recipients,
                    html_message=html_message,
                    fail_silently=False,
                )
                self.stdout.write(f'Sent expiry reminder for document "{document.title}"')
            except Exception as e:
                self.stderr.write(f'Failed to send expiry reminder for "{document.title}": {str(e)}')