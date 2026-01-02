from django.conf import settings
from django.db import models
from django.utils import timezone


class Appointment(models.Model):
	class AppointmentType(models.TextChoices):
		CONSULTATION = "consultation", "Consultation"
		PRINTING_JOB = "printing_job", "Printing job"
		IT_SUPPORT = "it_support", "IT support"

	class Status(models.TextChoices):
		PENDING = "pending", "Pending"
		CONFIRMED = "confirmed", "Confirmed"
		COMPLETED = "completed", "Completed"
		CANCELLED = "cancelled", "Cancelled"

	class MeetingMode(models.TextChoices):
		PHYSICAL = "physical", "Physical"
		GOOGLE_MEET = "google_meet", "Google Meet"
		WHATSAPP = "whatsapp", "WhatsApp"

	branch = models.ForeignKey(
		"core.Branch",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="appointments",
	)

	client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="appointments")
	assigned_to = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="assigned_appointments",
	)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="created_appointments",
	)

	appointment_type = models.CharField(max_length=30, choices=AppointmentType.choices)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
	scheduled_for = models.DateTimeField(default=timezone.now)
	meeting_mode = models.CharField(max_length=20, choices=MeetingMode.choices, default=MeetingMode.PHYSICAL)
	meeting_location = models.CharField(max_length=255, blank=True)
	meeting_link = models.URLField(blank=True)
	meeting_phone = models.CharField(max_length=50, blank=True)
	notes = models.TextField(blank=True)
	reminder_sent_at = models.DateTimeField(null=True, blank=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-scheduled_for"]

	def __str__(self):
		return f"{self.client} - {self.appointment_type} @ {self.scheduled_for:%Y-%m-%d %H:%M}"
