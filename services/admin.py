from django.contrib import admin

from .models import Service, ServiceCategory


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
	list_display = ("name", "is_active")
	list_filter = ("is_active",)
	search_fields = ("name",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
	list_display = ("name", "category", "branch", "unit_price", "service_charge", "profit_amount", "is_active", "updated_at")
	list_filter = ("is_active", "branch", "category")
	search_fields = ("name", "description")
