from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "branch",
            "client",
            "uploaded_by",
            "doc_type",
            "title",
            "file",
            "notes",
            "created_at",
        ]
        read_only_fields = ["uploaded_by", "created_at"]
