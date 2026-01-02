from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
	list_display = (
		"client",
		"appointment_type",
		"meeting_mode",
		"status",
		"scheduled_for",
		"assigned_to",
		"reminder_sent_at",
	)
	list_filter = ("appointment_type", "meeting_mode", "status", "reminder_sent_at")
	search_fields = ("client__company_name", "client__full_name", "assigned_to__email")
