from decimal import Decimal

from django.db import models


class ProfitRecord(models.Model):
	"""Stores profit/cost breakdown for a successfully completed (paid) invoice.

	Created when an invoice becomes PAID. If the invoice later becomes unpaid
	(e.g., due to refunds), the record is removed to keep reporting consistent.
	"""

	invoice = models.OneToOneField("invoices.Invoice", on_delete=models.CASCADE, related_name="profit_record")
	branch = models.ForeignKey("core.Branch", on_delete=models.SET_NULL, null=True, blank=True)
	currency = models.CharField(max_length=10, default="UGX")

	product_sales_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
	product_cost_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
	product_profit_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

	service_sales_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
	service_cost_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
	service_profit_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

	recorded_at = models.DateTimeField(auto_now_add=True)
	paid_at = models.DateTimeField(null=True, blank=True)
	trigger_payment = models.ForeignKey(
		"invoices.Payment",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="profit_records",
	)

	class Meta:
		ordering = ["-recorded_at", "-id"]
		indexes = [
			models.Index(fields=["branch", "-recorded_at"]),
		]

	def __str__(self) -> str:
		inv = getattr(self.invoice, "number", None) or f"Invoice {self.invoice_id}"
		return f"ProfitRecord for {inv}"
