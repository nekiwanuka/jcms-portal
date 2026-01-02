from django import forms
from django.utils import timezone

from .models import Appointment


class AppointmentForm(forms.ModelForm):
	"""Appointment create/edit form.

	- `created_by` is set in the view from the logged-in user.
	"""

	class Meta:
		model = Appointment
		exclude = ["created_by", "created_at", "updated_at", "reminder_sent_at"]
		widgets = {
			"scheduled_for": forms.DateTimeInput(attrs={"type": "datetime-local"}),
			"meeting_link": forms.URLInput(attrs={"placeholder": "https://meet.google.com/..."}),
			"meeting_phone": forms.TextInput(attrs={"placeholder": "+256..."}),
			"meeting_location": forms.TextInput(attrs={"placeholder": "Office address / room"}),
			"notes": forms.Textarea(attrs={"rows": 3}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")

	def clean(self):
		"""Appointment validation rules."""
		cleaned = super().clean()
		scheduled_for = cleaned.get("scheduled_for")
		status = cleaned.get("status")
		meeting_mode = cleaned.get("meeting_mode")
		meeting_link = (cleaned.get("meeting_link") or "").strip()
		meeting_phone = (cleaned.get("meeting_phone") or "").strip()
		meeting_location = (cleaned.get("meeting_location") or "").strip()

		# When creating/updating a pending/confirmed appointment, prevent accidental past scheduling.
		if scheduled_for and status in {Appointment.Status.PENDING, Appointment.Status.CONFIRMED}:
			if scheduled_for < timezone.now():
				self.add_error("scheduled_for", "Scheduled time must be in the future for pending/confirmed appointments.")

		# Meeting details validation
		if meeting_mode == Appointment.MeetingMode.GOOGLE_MEET and not meeting_link:
			self.add_error("meeting_link", "Please provide the Google Meet link.")
		if meeting_mode == Appointment.MeetingMode.WHATSAPP and not meeting_phone:
			self.add_error("meeting_phone", "Please provide the WhatsApp phone number.")
		if meeting_mode == Appointment.MeetingMode.PHYSICAL and not meeting_location:
			self.add_error("meeting_location", "Please provide the physical location.")

		return cleaned
