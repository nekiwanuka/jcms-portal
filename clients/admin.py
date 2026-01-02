from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
	list_display = ("id", "client_type", "company_name", "full_name", "phone", "email", "status")
	list_filter = ("client_type", "status")
	search_fields = ("company_name", "full_name", "phone", "email", "tin", "nin")
