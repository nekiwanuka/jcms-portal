from decimal import Decimal

from django.db import models


class ServiceCategory(models.Model):
	name = models.CharField(max_length=120, unique=True)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ["name"]

	def __str__(self) -> str:
		return self.name


class Service(models.Model):
	branch = models.ForeignKey(
		"core.Branch",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="services",
	)
	category = models.ForeignKey(
		"services.ServiceCategory",
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name="services",
	)
	name = models.CharField(max_length=255)
	description = models.TextField(blank=True, default="")
	# Selling price used on quotations/invoices.
	unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Sales price")
	# Internal cost/charge for delivering the service.
	service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Service charge")
	# Stored for reporting; kept in sync as (unit_price - service_charge).
	profit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Profit")
	is_active = models.BooleanField(default=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["name"]

	def __str__(self) -> str:
		return self.name

	def save(self, *args, **kwargs):
		# Keep profit consistent with pricing inputs.
		sales = (self.unit_price or Decimal("0.00")).quantize(Decimal("0.01"))
		charge = (self.service_charge or Decimal("0.00")).quantize(Decimal("0.01"))
		self.unit_price = sales
		self.service_charge = charge
		self.profit_amount = (sales - charge).quantize(Decimal("0.01"))
		super().save(*args, **kwargs)
