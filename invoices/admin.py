from django.contrib import admin

from .models import Invoice, InvoiceItem, Payment, PaymentRefund


class InvoiceItemInline(admin.TabularInline):
	model = InvoiceItem
	extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
	list_display = ("number", "client", "status", "issued_at", "due_at", "created_at")
	list_filter = ("status",)
	search_fields = ("number", "client__company_name", "client__full_name")
	inlines = [InvoiceItemInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
	list_display = ("invoice", "method_label", "amount", "reference", "paid_at")
	list_filter = ("method",)
	search_fields = ("invoice__number", "reference")


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
	list_display = ("invoice", "payment", "amount", "refunded_at", "refunded_by")
	list_filter = ("refunded_at",)
	search_fields = ("invoice__number", "payment__receipt_number", "reference")
