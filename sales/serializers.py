from rest_framework import serializers

from .models import Quotation, QuotationItem


class QuotationItemSerializer(serializers.ModelSerializer):
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = QuotationItem
        fields = ["id", "quotation", "product", "description", "quantity", "unit_price", "line_total"]

    def get_line_total(self, obj):
        return obj.line_total()


class QuotationSerializer(serializers.ModelSerializer):
    subtotal = serializers.SerializerMethodField()
    vat_amount = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = [
            "id",
            "branch",
            "client",
            "created_by",
            "number",
            "status",
            "currency",
            "vat_rate",
            "valid_until",
            "notes",
            "created_at",
            "updated_at",
            "subtotal",
            "vat_amount",
            "total",
        ]
        read_only_fields = ["number"]

    def get_subtotal(self, obj):
        return obj.subtotal()

    def get_vat_amount(self, obj):
        return obj.vat_amount()

    def get_total(self, obj):
        return obj.total()
