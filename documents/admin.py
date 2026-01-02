from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
	list_display = ("doc_type", "client", "title", "uploaded_by", "created_at")
	list_filter = ("doc_type",)
	search_fields = ("title", "client__company_name", "client__full_name", "uploaded_by__email")
