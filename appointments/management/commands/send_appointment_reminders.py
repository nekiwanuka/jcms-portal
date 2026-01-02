from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db import transaction
from django.utils import timezone

from appointments.models import Appointment


class Command(BaseCommand):
	help = "Send appointment reminder emails for upcoming appointments."

	def add_arguments(self, parser):
		parser.add_argument(
			"--lead-minutes",
			type=int,
			default=getattr(settings, "APPOINTMENT_REMINDER_LEAD_MINUTES", 24 * 60),
			help="How long before scheduled time to send the reminder (default: 1440).",
		)
		parser.add_argument(
			"--window-minutes",
			type=int,
			default=getattr(settings, "APPOINTMENT_REMINDER_WINDOW_MINUTES", 30),
			help="Window size for matching reminders (default: 30).",
		)
		parser.add_argument(
			"--dry-run",
			action="store_true",
			help="Do not send emails; just show what would be sent.",
		)

	def handle(self, *args, **options):
		lead_minutes: int = options["lead_minutes"]
		window_minutes: int = options["window_minutes"]
		dry_run: bool = options["dry_run"]

		now = timezone.now()
		start = now + timedelta(minutes=lead_minutes)
		end = start + timedelta(minutes=window_minutes)

		qs = (
			Appointment.objects.select_related("client", "assigned_to", "branch")
			.filter(
				status__in=[Appointment.Status.PENDING, Appointment.Status.CONFIRMED],
				scheduled_for__gte=start,
				scheduled_for__lt=end,
				reminder_sent_at__isnull=True,
			)
			.order_by("scheduled_for")
		)

		count = qs.count()
		self.stdout.write(
			f"Found {count} appointment(s) needing reminders between {start:%Y-%m-%d %H:%M} and {end:%Y-%m-%d %H:%M}."
		)

		sent = 0
		for appt in qs:
			to_emails: list[str] = []

			client_email = (appt.client.email or "").strip() if appt.client_id else ""
			if client_email:
				to_emails.append(client_email)

			staff_email = (getattr(appt.assigned_to, "email", "") or "").strip()
			if staff_email and staff_email not in to_emails:
				to_emails.append(staff_email)

			if not to_emails:
				self.stdout.write(
					self.style.WARNING(
						f"Skipping appointment #{appt.pk}: no recipient email (client/staff missing)."
					)
				)
				continue

			scheduled_local = timezone.localtime(appt.scheduled_for)
			branch_name = str(appt.branch) if appt.branch_id else "-"
			branch_address = (getattr(appt.branch, "address", "") or "").strip() if appt.branch_id else ""

			meeting_mode_label = appt.get_meeting_mode_display()
			meeting_location = (appt.meeting_location or "").strip() or branch_address
			meeting_link = (appt.meeting_link or "").strip()
			meeting_phone = (appt.meeting_phone or "").strip() or (appt.client.phone or "").strip()

			subject = (
				f"Appointment Reminder: {appt.get_appointment_type_display()} "
				f"({scheduled_local:%Y-%m-%d %H:%M})"
			)
			ctx = {
				"client_name": str(appt.client),
				"appointment_type": appt.get_appointment_type_display(),
				"status": appt.get_status_display(),
				"scheduled_at": scheduled_local.strftime("%Y-%m-%d %H:%M"),
				"branch_name": branch_name,
				"meeting_mode": meeting_mode_label,
				"meeting_location": meeting_location,
				"meeting_link": meeting_link,
				"meeting_phone": meeting_phone,
				"notes": (appt.notes or "").strip(),
			}

			text_body = render_to_string("appointments/reminder_email.txt", ctx)
			html_body = render_to_string("appointments/reminder_email.html", ctx)

			if dry_run:
				self.stdout.write(f"DRY RUN: would email {to_emails} for appointment #{appt.pk}")
				continue

			try:
				email = EmailMultiAlternatives(
					subject=subject,
					body=text_body,
					from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
					to=to_emails,
				)
				email.attach_alternative(html_body, "text/html")
				email.send(fail_silently=False)
			except Exception as exc:
				self.stdout.write(self.style.ERROR(f"Failed sending appointment #{appt.pk}: {exc}"))
				continue

			with transaction.atomic():
				Appointment.objects.filter(pk=appt.pk, reminder_sent_at__isnull=True).update(reminder_sent_at=now)

			sent += 1

		self.stdout.write(self.style.SUCCESS(f"Reminders sent: {sent}"))
