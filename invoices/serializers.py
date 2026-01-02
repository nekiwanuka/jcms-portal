from rest_framework import serializers

from .models import Invoice, InvoiceItem, Payment


class InvoiceItemSerializer(serializers.ModelSerializer):
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceItem
        fields = ["id", "invoice", "product", "description", "quantity", "unit_price", "line_total"]

    def get_line_total(self, obj):
        return obj.line_total()


class PaymentSerializer(serializers.ModelSerializer):
    method_label = serializers.CharField(read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "method",
            "method_other",
            "method_label",
            "amount",
            "reference",
            "paid_at",
            "recorded_by",
            "notes",
            "created_at",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    subtotal = serializers.SerializerMethodField()
    vat_amount = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()
    outstanding_balance = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "branch",
            "client",
            "quotation",
            "created_by",
            "number",
            "status",
            "currency",
            "vat_rate",
            "issued_at",
            "due_at",
            "notes",
            "created_at",
            "updated_at",
            "subtotal",
            "vat_amount",
            "total",
            "amount_paid",
            "outstanding_balance",
        ]
        read_only_fields = ["number"]

    def get_subtotal(self, obj):
        return obj.subtotal()

    def get_vat_amount(self, obj):
        return obj.vat_amount()

    def get_total(self, obj):
        return obj.total()

    def get_amount_paid(self, obj):
        return obj.amount_paid()

    def get_outstanding_balance(self, obj):
        return obj.outstanding_balance()
