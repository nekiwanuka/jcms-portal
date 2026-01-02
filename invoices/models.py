from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


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

	# Printing / approval fields
	prepared_by_name = models.CharField(max_length=120, blank=True, default="")
	signed_by_name = models.CharField(max_length=120, blank=True, default="")
	signed_at = models.DateTimeField(null=True, blank=True)

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

	def vat_amount(self) -> Decimal:
		return (self.subtotal() * self.vat_rate).quantize(Decimal("0.01"))

	def total(self) -> Decimal:
		return (self.subtotal() + self.vat_amount()).quantize(Decimal("0.01"))

	def amount_paid(self) -> Decimal:
		return sum((p.amount for p in self.payments.all()), Decimal("0.00")).quantize(Decimal("0.01"))

	def outstanding_balance(self) -> Decimal:
		return (self.total() - self.amount_paid()).quantize(Decimal("0.01"))

	def refresh_status_from_payments(self, *, save: bool = True) -> None:
		"""Keep invoice status consistent with payments.

		Rules:
		- If CANCELLED, do not auto-change.
		- If outstanding balance is <= 0 -> PAID.
		- If some amount is paid and invoice is DRAFT -> ISSUED.
		"""
		if self.status == self.Status.CANCELLED:
			return

		paid = self.amount_paid()
		balance = self.outstanding_balance()

		new_status = self.status
		if balance <= Decimal("0.00"):
			new_status = self.Status.PAID
		elif paid > Decimal("0.00") and self.status == self.Status.DRAFT:
			new_status = self.Status.ISSUED

		update_fields: list[str] = []
		if new_status != self.status:
			self.status = new_status
			update_fields.append("status")

		if self.status == self.Status.ISSUED and not self.issued_at:
			self.issued_at = timezone.localdate()
			update_fields.append("issued_at")

		if save and update_fields:
			self.save(update_fields=update_fields)


class InvoiceItem(models.Model):
	invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
	product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, null=True, blank=True)
	description = models.CharField(max_length=255)
	quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1.00"))
	unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

	def __str__(self):
		return self.description

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
			except Exception:
				# Avoid failing payment save if invoice status refresh hits a race.
				pass
