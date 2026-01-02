from django.contrib import admin

from .models import Quotation, QuotationItem


class QuotationItemInline(admin.TabularInline):
	model = QuotationItem
	extra = 1


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
	list_display = ("number", "client", "status", "created_at")
	list_filter = ("status",)
	search_fields = ("number", "client__company_name", "client__full_name")
	inlines = [QuotationItemInline]
