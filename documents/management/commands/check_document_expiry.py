from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from documents.models import Document
from django.template.loader import render_to_string


class Command(BaseCommand):
    help = 'Check for expiring documents and send notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=30,
            help='Number of days ahead to check for expiry (default: 30)',
        )
        parser.add_argument(
            '--send-notifications',
            action='store_true',
            help='Send email notifications for expiring documents',
        )

    def handle(self, *args, **options):
        days_ahead = options['days_ahead']
        send_notifications = options['send_notifications']

        # Calculate the date threshold
        threshold_date = timezone.now().date() + timezone.timedelta(days=days_ahead)

        # Find documents that will expire within the threshold
        expiring_documents = Document.objects.filter(
            expiry_date__lte=threshold_date,
            expiry_date__gte=timezone.now().date(),
            verification_status__in=['approved', 'pending']
        ).select_related('client', 'uploaded_by')

        # Find already expired documents
        expired_documents = Document.objects.filter(
            expiry_date__lt=timezone.now().date(),
            verification_status__in=['approved', 'pending']
        ).select_related('client', 'uploaded_by')

        self.stdout.write(
            f'Found {expiring_documents.count()} documents expiring within {days_ahead} days'
        )
        self.stdout.write(f'Found {expired_documents.count()} expired documents')

        if send_notifications:
            # Send notifications for expiring documents
            for doc in expiring_documents:
                self.send_expiry_notification(doc, days_ahead)

            # Send notifications for expired documents
            for doc in expired_documents:
                self.send_expired_notification(doc)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Sent notifications for {expiring_documents.count() + expired_documents.count()} documents'
                )
            )
        else:
            # Just list the documents
            if expiring_documents:
                self.stdout.write('\nDocuments expiring soon:')
                for doc in expiring_documents:
                    days_left = (doc.expiry_date - timezone.now().date()).days
                    self.stdout.write(
                        f'  - {doc.title} (Client: {doc.client.name}, Expires: {doc.expiry_date}, Days left: {days_left})'
                    )

            if expired_documents:
                self.stdout.write('\nExpired documents:')
                for doc in expired_documents:
                    days_expired = (timezone.now().date() - doc.expiry_date).days
                    self.stdout.write(
                        f'  - {doc.title} (Client: {doc.client.name}, Expired: {doc.expiry_date}, Days expired: {days_expired})'
                    )

    def send_expiry_notification(self, document, days_ahead):
        """Send notification for document expiring soon."""
        subject = f'Document Expiring Soon: {document.title}'

        context = {
            'document': document,
            'days_ahead': days_ahead,
            'days_until_expiry': document.days_until_expiry,
            'expiry_date': document.expiry_date,
        }

        html_message = render_to_string('emails/document_expiring.html', context)
        plain_message = render_to_string('emails/document_expiring.txt', context)

        # Send to document uploader and any approved users
        recipients = []
        if document.uploaded_by and document.uploaded_by.email:
            recipients.append(document.uploaded_by.email)

        for user in document.approved_by.all():
            if user.email and user.email not in recipients:
                recipients.append(user.email)

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
                self.stdout.write(
                    f'  Sent expiry notification for: {document.title}'
                )
            except Exception as e:
                self.stderr.write(
                    f'  Failed to send expiry notification for {document.title}: {str(e)}'
                )

    def send_expired_notification(self, document):
        """Send notification for expired document."""
        subject = f'Document Expired: {document.title}'

        context = {
            'document': document,
            'days_expired': (timezone.now().date() - document.expiry_date).days,
            'expiry_date': document.expiry_date,
        }

        html_message = render_to_string('emails/document_expired.html', context)
        plain_message = render_to_string('emails/document_expired.txt', context)

        # Send to document uploader and any approved users
        recipients = []
        if document.uploaded_by and document.uploaded_by.email:
            recipients.append(document.uploaded_by.email)

        for user in document.approved_by.all():
            if user.email and user.email not in recipients:
                recipients.append(user.email)

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
                self.stdout.write(
                    f'  Sent expired notification for: {document.title}'
                )
            except Exception as e:
                self.stderr.write(
                    f'  Failed to send expired notification for {document.title}: {str(e)}'
                )