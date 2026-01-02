from rest_framework import serializers

from .models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = [
            "id",
            "branch",
            "client",
            "assigned_to",
            "created_by",
            "appointment_type",
            "status",
            "scheduled_for",
            "notes",
            "created_at",
            "updated_at",
        ]
