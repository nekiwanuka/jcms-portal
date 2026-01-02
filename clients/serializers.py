from rest_framework import serializers

from .models import Client


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "id",
            "branch",
            "client_type",
            "full_name",
            "company_name",
            "contact_person",
            "phone",
            "email",
            "physical_address",
            "tin",
            "nin",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
