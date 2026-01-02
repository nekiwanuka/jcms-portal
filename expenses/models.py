from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Expense(models.Model):
	class Category(models.TextChoices):
		RENT = "rent", "Rent"
		UTILITIES = "utilities", "Utilities"
		SALARIES = "salaries", "Salaries"
		TRANSPORT = "transport", "Transport"
		SUPPLIES = "supplies", "Supplies"
		MAINTENANCE = "maintenance", "Maintenance"
		OTHER = "other", "Other"

	branch = models.ForeignKey(
		"core.Branch",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="expenses",
	)
	category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
	category_other = models.CharField(max_length=120, blank=True, default="", verbose_name="Other (specify)")
	description = models.CharField(max_length=255)
	amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
	expense_date = models.DateField(default=timezone.localdate)
	reference = models.CharField(max_length=120, blank=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-expense_date", "-id"]

	def __str__(self) -> str:
		return f"{self.expense_date} {self.category} {self.amount}"

	@property
	def category_label(self) -> str:
		if self.category == self.Category.OTHER and (self.category_other or "").strip():
			return self.category_other.strip()
		return self.get_category_display()
