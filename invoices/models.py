from decimal import Decimal
import logging

from django.conf import settings
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone


logger = logging.getLogger(__name__)


class InvoiceSequence(models.Model):
	year = models.PositiveIntegerField(unique=True)
	last_number = models.PositiveIntegerField(default=0)


class Invoice(models.Model):
	class Status(models.TextChoices):
		DRAFT = "draft", "Draft"
		ISSUED = "issued", "Issued"
		PAID = "paid", "Paid"
		CANCELLED = "cancelled", "Cancelled"

	branch = models.ForeignKey(
		"core.Branch",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="invoices",
	)
	client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="invoices")
	quotation = models.OneToOneField("sales.Quotation", on_delete=models.SET_NULL, null=True, blank=True, related_name="invoice")
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

	number = models.CharField(max_length=30, unique=True, blank=True)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

	currency = models.CharField(max_length=10, default=getattr(settings, "DEFAULT_CURRENCY", "UGX"))
	vat_rate = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal(str(getattr(settings, "DEFAULT_VAT_RATE", "0.18"))))

	issued_at = models.DateField(null=True, blank=True)
	due_at = models.DateField(null=True, blank=True)
	notes = models.TextField(blank=True)

	# Cancellation metadata (audit-friendly; avoids deleting history)
	cancelled_at = models.DateTimeField(null=True, blank=True)
	cancelled_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="cancelled_invoices",
	)
	cancel_reason = models.TextField(blank=True, default="")

	# Printing / approval fields
	prepared_by_name = models.CharField(max_length=120, blank=True, default="")
	signed_by_name = models.CharField(max_length=120, blank=True, default="")
	signed_at = models.DateTimeField(null=True, blank=True)

	# Inventory integration
	stock_deducted_at = models.DateTimeField(null=True, blank=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return self.number or f"Invoice #{self.pk}"

	def _next_number(self) -> str:
		year = timezone.localdate().year
		with transaction.atomic():
			seq, _ = InvoiceSequence.objects.select_for_update().get_or_create(year=year)
			seq.last_number += 1
			seq.save(update_fields=["last_number"])
			return f"INV-{year}-{seq.last_number:05d}"

	def save(self, *args, **kwargs):
		if not self.number:
			self.number = self._next_number()
		super().save(*args, **kwargs)

	def subtotal(self) -> Decimal:
		return sum((item.line_total() for item in self.items.all()), Decimal("0.00"))

	def taxable_subtotal(self) -> Decimal:
		return sum((item.line_total() for item in self.items.filter(vat_exempt=False)), Decimal("0.00"))

	def vat_amount(self) -> Decimal:
		return (self.taxable_subtotal() * (self.vat_rate or Decimal("0.00"))).quantize(Decimal("0.01"))

	def total(self) -> Decimal:
		return (self.subtotal() + self.vat_amount()).quantize(Decimal("0.01"))

	def amount_paid(self) -> Decimal:
		paid = sum((p.amount for p in self.payments.all()), Decimal("0.00"))
		refunded = sum((r.amount for r in self.refunds.all()), Decimal("0.00"))
		return (paid - refunded).quantize(Decimal("0.01"))

	def amount_refunded(self) -> Decimal:
		return sum((r.amount for r in self.refunds.all()), Decimal("0.00")).quantize(Decimal("0.01"))

	def outstanding_balance(self) -> Decimal:
		"""Return the remaining balance, tolerating tiny rounding differences.

		In some cases VAT/line rounding can leave a very small residual even when
		the user has effectively paid the "full" amount. Treat very small
		differences (<= 0.05) as fully paid so the UI does not show a
		confusing 0.01 balance.
		"""
		balance = (self.total() - self.amount_paid()).quantize(Decimal("0.01"))
		if abs(balance) <= Decimal("0.05"):
			return Decimal("0.00")
		return balance

	def refresh_status_from_payments(self, *, save: bool = True) -> None:
		"""Keep invoice status consistent with payments.

		Rules:
		- If CANCELLED, do not auto-change.
		- If outstanding balance is <= 0 -> PAID.
		- If some amount is paid -> ISSUED.
		- If no amount is paid:
		  - stay ISSUED if the invoice was already issued (sent/paid/refunded)
		  - otherwise remain DRAFT.
		"""
		if self.status == self.Status.CANCELLED:
			return

		paid = self.amount_paid()
		balance = self.outstanding_balance()

		was_issued = bool(self.issued_at) or self.status in {self.Status.ISSUED, self.Status.PAID}
		if not was_issued:
			# If there is any payment/refund history, treat as issued (even if net is now 0).
			try:
				was_issued = self.payments.exists() or self.refunds.exists()
			except Exception:
				was_issued = was_issued

		new_status = self.status
		if balance <= Decimal("0.00"):
			new_status = self.Status.PAID
		elif paid > Decimal("0.00"):
			new_status = self.Status.ISSUED
		else:
			new_status = self.Status.ISSUED if was_issued else self.Status.DRAFT

		update_fields: list[str] = []
		if new_status != self.status:
			self.status = new_status
			update_fields.append("status")

		if self.status == self.Status.ISSUED and not self.issued_at:
			self.issued_at = timezone.localdate()
			update_fields.append("issued_at")

		if save and update_fields:
			self.save(update_fields=update_fields)
		# If the invoice is now paid, attempt stock deduction.
		try:
			self.deduct_stock_if_needed()
		except Exception:
			logger.exception("Failed to deduct stock for invoice %s", self.pk)
		# If paid/unpaid state changed, keep profit record consistent.
		try:
			self._sync_profit_record()
		except Exception:
			logger.exception("Failed to sync profit record for invoice %s", self.pk)

	def _compute_profit_breakdown(self) -> dict:
		"""Compute sales/cost/profit totals for products and services on this invoice.

		- Product cost is taken from InvoiceItem.unit_cost (snapshot); if 0, falls back to Product.cost_price.
		- Service cost is taken from Service.service_charge at time of report.
		"""
		items = list(self.items.select_related("product", "service").all())
		product_sales = Decimal("0.00")
		product_cost = Decimal("0.00")
		product_profit = Decimal("0.00")
		service_sales = Decimal("0.00")
		service_cost = Decimal("0.00")
		service_profit = Decimal("0.00")

		for it in items:
			qty = (it.quantity or Decimal("0.00"))
			if qty <= Decimal("0.00"):
				continue
			unit_price = (it.unit_price or Decimal("0.00"))
			line_sales = (qty * unit_price).quantize(Decimal("0.01"))

			if it.product_id:
				unit_cost = (it.unit_cost or Decimal("0.00"))
				if unit_cost == Decimal("0.00") and it.product is not None:
					unit_cost = (getattr(it.product, "cost_price", None) or Decimal("0.00"))
				line_cost = (qty * unit_cost).quantize(Decimal("0.01"))
				product_sales += line_sales
				product_cost += line_cost
				product_profit += (line_sales - line_cost)
				continue

			if it.service_id and it.service is not None:
				unit_charge = (getattr(it.service, "service_charge", None) or Decimal("0.00"))
				line_cost = (qty * unit_charge).quantize(Decimal("0.01"))
				service_sales += line_sales
				service_cost += line_cost
				service_profit += (line_sales - line_cost)
				continue

		return {
			"product_sales_total": product_sales.quantize(Decimal("0.01")),
			"product_cost_total": product_cost.quantize(Decimal("0.01")),
			"product_profit_total": product_profit.quantize(Decimal("0.01")),
			"service_sales_total": service_sales.quantize(Decimal("0.01")),
			"service_cost_total": service_cost.quantize(Decimal("0.01")),
			"service_profit_total": service_profit.quantize(Decimal("0.01")),
		}

	def _sync_profit_record(self, *, trigger_payment=None) -> None:
		"""Create or remove ProfitRecord depending on whether invoice is PAID."""
		if not self.pk:
			return
		from reports.models import ProfitRecord

		if self.status == self.Status.PAID:
			values = self._compute_profit_breakdown()
			defaults = {
				"branch_id": self.branch_id,
				"currency": self.currency or "UGX",
				"paid_at": timezone.now(),
				**values,
			}
			if trigger_payment is not None:
				defaults["trigger_payment"] = trigger_payment
			ProfitRecord.objects.update_or_create(invoice_id=self.pk, defaults=defaults)
			return

		# If invoice is not PAID, remove any existing profit record.
		ProfitRecord.objects.filter(invoice_id=self.pk).delete()

	@property
	def is_approved(self) -> bool:
		return bool(self.signed_at)

	def deduct_stock_if_needed(self) -> bool:
		"""Deduct inventory stock exactly once when invoice is paid.

		Rules:
		- Only when `status == PAID`.
		- Deduct only for line-items linked to a Product.
		- Idempotent via `stock_deducted_at`.
		- Idempotent via `stock_deducted_at`.
		"""
		if not self.pk:
			return False
		if self.status != self.Status.PAID:
			return False

		from inventory.models import Product, StockMovement

		with transaction.atomic():
			invoice = Invoice.objects.select_for_update().get(pk=self.pk)
			reference = invoice.number or f"Invoice {invoice.pk}"
			# Repair path: previous versions could mark stock_deducted_at even when
			# there were no eligible items (or before items were added). If we have
			# no OUT movements recorded for this invoice, allow re-running deduction.
			if invoice.stock_deducted_at and StockMovement.objects.filter(
				reference=reference,
				movement_type=StockMovement.MovementType.OUT,
			).exists():
				return False
			if invoice.status != self.Status.PAID:
				return False

			items = list(invoice.items.select_related("product").all())
			deducted_any = False
			for item in items:
				if not item.product_id:
					continue
				qty = (item.quantity or Decimal("0.00"))
				if qty <= Decimal("0.00"):
					continue
				# Update stock and record a movement. Allow negative stock if oversold.
				Product.objects.filter(pk=item.product_id).update(stock_quantity=F("stock_quantity") - qty)
				StockMovement.objects.create(
					product_id=item.product_id,
					movement_type=StockMovement.MovementType.OUT,
					quantity=qty,
					reference=reference,
					notes=f"Sold via invoice {invoice.number or invoice.pk}",
					occurred_at=timezone.now(),
				)
				deducted_any = True

			if not deducted_any:
				return False

			invoice.stock_deducted_at = timezone.now()
			invoice.save(update_fields=["stock_deducted_at"])
			self.stock_deducted_at = invoice.stock_deducted_at
		return True


class InvoiceItem(models.Model):
	invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
	product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, null=True, blank=True)
	service = models.ForeignKey("services.Service", on_delete=models.PROTECT, null=True, blank=True)
	description = models.CharField(max_length=255)
	quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1.00"))
	unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
	unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
	vat_exempt = models.BooleanField(default=False)

	def __str__(self):
		return self.description

	def save(self, *args, **kwargs):
		super().save(*args, **kwargs)
		if self.invoice_id:
			try:
				# If an item is added/edited after payment, ensure stock is deducted.
				self.invoice.deduct_stock_if_needed()
			except Exception:
				logger.exception("Failed to deduct stock after saving invoice item %s", self.pk)

	def line_total(self) -> Decimal:
		return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


class Payment(models.Model):
	class Method(models.TextChoices):
		CASH = "cash", "Cash"
		BANK = "bank", "Bank"
		MOBILE_MONEY = "mobile_money", "Mobile Money"
		OTHER = "other", "Other"

	invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
	method = models.CharField(max_length=20, choices=Method.choices)
	method_other = models.CharField(max_length=120, blank=True, default="")
	amount = models.DecimalField(max_digits=12, decimal_places=2)
	receipt_number = models.CharField(max_length=40, unique=True, blank=True, default="", db_index=True)
	reference = models.CharField(max_length=120, blank=True)
	paid_at = models.DateTimeField(default=timezone.now)
	recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	notes = models.TextField(blank=True)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-paid_at", "-id"]

	def __str__(self):
		return f"{self.invoice.number} {self.amount} {self.method_label}"

	@property
	def method_label(self) -> str:
		if self.method == self.Method.OTHER:
			label = (self.method_other or "").strip()
			return label or "Other"
		return self.get_method_display()

	def save(self, *args, **kwargs):
		super().save(*args, **kwargs)

		# Generate a stable receipt number after PK exists.
		if not self.receipt_number and self.pk:
			paid_date = timezone.localtime(self.paid_at).date()
			receipt_number = f"RCPT-{paid_date:%Y%m%d}-{self.pk:06d}"
			Payment.objects.filter(pk=self.pk, receipt_number="").update(receipt_number=receipt_number)
			self.receipt_number = receipt_number

		# Ensure invoice status stays consistent.
		if self.invoice_id:
			try:
				self.invoice.refresh_status_from_payments(save=True)
				# Attach this payment to the profit record if the invoice became PAID.
				try:
					self.invoice._sync_profit_record(trigger_payment=self)
				except Exception:
					pass
			except Exception:
				# Avoid failing payment save if invoice status refresh hits a race.
				pass

	@property
	def refund_deadline(self):
		"""Latest datetime a refund may be created for this payment.

		Policy: refunds are allowed within 21 days of the payment date.
		"""
		return self.paid_at + timezone.timedelta(days=21)

	@property
	def is_refund_window_open(self) -> bool:
		return timezone.now() <= self.refund_deadline


class PaymentRefund(models.Model):
	"""Represents a refund against a recorded payment.

	We keep refunds separate from `Payment` to preserve the meaning that payments
	are positive receipts. Refunds reduce net revenue and increase invoice balance.
	"""

	payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refunds")
	invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="refunds")
	amount = models.DecimalField(max_digits=12, decimal_places=2)
	refunded_at = models.DateTimeField(default=timezone.now)
	refunded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	reference = models.CharField(max_length=120, blank=True, default="")
	notes = models.TextField(blank=True, default="")

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-refunded_at", "-id"]
		indexes = [
			models.Index(fields=["invoice", "-refunded_at"], name="invoices_pa_invoice_61cc52_idx"),
			models.Index(fields=["payment", "-refunded_at"], name="invoices_pa_payment_d1987f_idx"),
		]

	def __str__(self):
		inv = getattr(self.invoice, "number", None) or f"Invoice {self.invoice_id}"
		return f"Refund {self.amount} for {inv}"

	def clean(self):
		from django.core.exceptions import ValidationError
		if self.amount is None or self.amount <= Decimal("0.00"):
			raise ValidationError({"amount": "Refund amount must be greater than 0."})

		# Policy: refunds can only be created within 21 days of the payment date.
		# Enforce against current time to prevent backdating.
		if self.payment_id and getattr(self.payment, "paid_at", None):
			deadline = self.payment.paid_at + timezone.timedelta(days=21)
			if timezone.now() > deadline:
				deadline_local = timezone.localtime(deadline)
				raise ValidationError(
					f"Refund window expired. Refunds are allowed within 21 days of payment date (deadline: {deadline_local:%Y-%m-%d %H:%M})."
				)

		# Ensure refund is consistent with linked objects.
		if self.payment_id and self.invoice_id and self.payment.invoice_id != self.invoice_id:
			raise ValidationError("Refund invoice must match payment invoice.")

		# Prevent over-refunding the payment.
		if self.payment_id:
			already_refunded = (
				PaymentRefund.objects.filter(payment_id=self.payment_id)
				.exclude(pk=self.pk)
				.aggregate(total=models.Sum("amount"))
				.get("total")
				or Decimal("0.00")
			)
			payment_amount = getattr(self.payment, "amount", None) or Decimal("0.00")
			if already_refunded + (self.amount or Decimal("0.00")) > payment_amount:
				refundable = payment_amount - already_refunded
				if refundable < Decimal("0.00"):
					refundable = Decimal("0.00")
				raise ValidationError({"amount": f"Refund cannot exceed refundable amount ({refundable})."})

	def save(self, *args, **kwargs):
		# Keep invoice in sync even when refunds are edited/deleted.
		self.full_clean()
		super().save(*args, **kwargs)
		if self.invoice_id:
			try:
				self.invoice.refresh_status_from_payments(save=True)
			except Exception:
				logger.exception("Failed to refresh invoice status after refund %s", self.pk)
