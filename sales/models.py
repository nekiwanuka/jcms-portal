from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class QuotationSequence(models.Model):
	year = models.PositiveIntegerField(unique=True)
	last_number = models.PositiveIntegerField(default=0)


class Quotation(models.Model):
	class Category(models.TextChoices):
		PRINTING = "printing", "Printing"
		BRANDING = "branding", "Branding"
		IT = "it", "IT"
		MEDICAL = "medical", "Medical"
		PPE = "ppe", "PPE"
		GENERAL_SUPPLIES = "general_supplies", "General Supplies"
		OTHER = "other", "Other"

	class Status(models.TextChoices):
		DRAFT = "draft", "Draft"
		SENT = "sent", "Sent"
		ACCEPTED = "accepted", "Approved"
		REJECTED = "rejected", "Rejected"
		CONVERTED = "converted", "Converted"
		EXPIRED = "expired", "Expired"
		CANCELLED = "cancelled", "Cancelled"

	branch = models.ForeignKey(
		"core.Branch",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="quotations",
	)
	client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="quotations")
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

	number = models.CharField(max_length=30, unique=True, blank=True)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

	category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
	category_other = models.CharField(max_length=120, blank=True, default="", verbose_name="Other (specify)")

	currency = models.CharField(max_length=10, default=getattr(settings, "DEFAULT_CURRENCY", "UGX"))
	vat_rate = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal(str(getattr(settings, "DEFAULT_VAT_RATE", "0.18"))))
	vat_enabled = models.BooleanField(default=True)
	discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

	subtotal_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
	vat_amount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
	total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

	valid_until = models.DateField(null=True, blank=True)
	notes = models.TextField(blank=True)

	# Cancellation metadata (audit-friendly; avoids deleting history)
	cancelled_at = models.DateTimeField(null=True, blank=True)
	cancelled_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="cancelled_quotations",
	)
	cancel_reason = models.TextField(blank=True, default="")

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return self.number or f"Quotation #{self.pk}"

	def _next_number(self) -> str:
		"""Generate the next quotation number.

		On some shared-host deployments, database locking/privileges can be quirky.
		If sequence increment fails for any reason, fall back to a timestamp-based
		identifier so the request doesn't 500.
		"""
		year = timezone.localdate().year
		try:
			with transaction.atomic():
				seq, _ = QuotationSequence.objects.select_for_update().get_or_create(year=year)
				seq.last_number += 1
				seq.save(update_fields=["last_number"])
				return f"Q-{year}-{seq.last_number:05d}"
		except Exception:
			# Fallback keeps numbers unique-ish without relying on the sequence table.
			ts = int(timezone.now().timestamp())
			return f"Q-{year}-{ts}"

	def save(self, *args, **kwargs):
		if not self.number:
			self.number = self._next_number()
		super().save(*args, **kwargs)

	def is_expired(self) -> bool:
		if not self.valid_until:
			return False
		return timezone.localdate() > self.valid_until

	def refresh_expiry_status(self, *, save: bool = True) -> bool:
		"""Auto-expire Draft/Sent quotations after validity date."""
		if self.is_expired() and self.status in {self.Status.DRAFT, self.Status.SENT}:
			self.status = self.Status.EXPIRED
			if save:
				self.save(update_fields=["status"])
			return True
		return False

	def recalculate_amounts(self, *, save: bool = True) -> None:
		"""Recalculate and store subtotal/vat/total based on items and toggles."""
		subtotal = sum((item.line_total() for item in self.items.all()), Decimal("0.00"))
		taxable_subtotal = sum((item.line_total() for item in self.items.filter(vat_exempt=False)), Decimal("0.00"))
		discount = (self.discount_amount or Decimal("0.00")).quantize(Decimal("0.01"))
		if discount < Decimal("0.00"):
			discount = Decimal("0.00")
		pre_tax_total = (subtotal - discount)
		if pre_tax_total < Decimal("0.00"):
			pre_tax_total = Decimal("0.00")

		taxable_base = (taxable_subtotal - discount)
		if taxable_base < Decimal("0.00"):
			taxable_base = Decimal("0.00")

		vat_rate = (self.vat_rate or Decimal("0.00"))
		vat = (taxable_base * vat_rate).quantize(Decimal("0.01")) if (self.vat_enabled and vat_rate) else Decimal("0.00")
		total = (pre_tax_total + vat).quantize(Decimal("0.01"))

		self.subtotal_amount = subtotal.quantize(Decimal("0.01"))
		self.vat_amount_amount = vat
		self.total_amount = total

		if save and self.pk:
			self.save(update_fields=["subtotal_amount", "vat_amount_amount", "total_amount", "updated_at"])

	def subtotal(self) -> Decimal:
		return (self.subtotal_amount or Decimal("0.00")).quantize(Decimal("0.01"))

	def vat_amount(self) -> Decimal:
		return (self.vat_amount_amount or Decimal("0.00")).quantize(Decimal("0.01"))

	def total(self) -> Decimal:
		return (self.total_amount or Decimal("0.00")).quantize(Decimal("0.01"))

	@property
	def category_label(self) -> str:
		if self.category == self.Category.OTHER and (self.category_other or "").strip():
			return self.category_other.strip()
		return self.get_category_display()

	@property
	def badge_class(self) -> str:
		return {
			self.Status.DRAFT: "text-bg-warning",
			self.Status.SENT: "text-bg-primary",
			self.Status.ACCEPTED: "text-bg-success",
			self.Status.REJECTED: "text-bg-danger",
			self.Status.CONVERTED: "text-bg-secondary",
			self.Status.EXPIRED: "text-bg-dark",
			self.Status.CANCELLED: "text-bg-danger",
		}.get(self.status, "text-bg-secondary")


class QuotationItem(models.Model):
	quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="items")
	product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, null=True, blank=True)
	service = models.ForeignKey("services.Service", on_delete=models.PROTECT, null=True, blank=True)
	item_name = models.CharField(max_length=255, blank=True, default="")
	description = models.CharField(max_length=255, blank=True, default="")
	quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1.00"))
	unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
	vat_exempt = models.BooleanField(default=False)
	total_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

	def __str__(self):
		return self.item_name or self.description

	def line_total(self) -> Decimal:
		return (self.quantity * self.unit_price).quantize(Decimal("0.01"))

	def save(self, *args, **kwargs):
		if not self.item_name and self.description:
			self.item_name = self.description
		self.total_price = self.line_total()
		super().save(*args, **kwargs)
		if self.quotation_id:
			try:
				self.quotation.recalculate_amounts(save=True)
			except Exception:
				pass

	def delete(self, *args, **kwargs):
		quotation = self.quotation
		ret = super().delete(*args, **kwargs)
		if quotation and quotation.pk:
			try:
				quotation.recalculate_amounts(save=True)
			except Exception:
				pass
		return ret
