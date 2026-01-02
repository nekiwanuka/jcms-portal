from django.contrib import admin

from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
	list_display = ("expense_date", "branch", "category", "description", "amount", "reference", "created_by")
	list_filter = ("category", "branch")
	search_fields = ("description", "reference")
