from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import Invoice, InvoiceItem, Payment, PaymentRefund


class InvoiceForm(forms.ModelForm):
	"""Invoice create/edit form.

	- `number` is auto-generated in the model, so it is excluded.
	- `created_by` is set in the view from the logged-in user.
	- UI exposes a simple checkbox to apply VAT at a fixed 18%.
	"""

	apply_vat = forms.BooleanField(required=False, label="Apply VAT (18%)")

	class Meta:
		model = Invoice
		exclude = [
			"number",
			"created_by",
			"created_at",
			"updated_at",
			"prepared_by_name",
			"signed_by_name",
			"signed_at",
		]
		widgets = {
			"issued_at": forms.DateInput(attrs={"type": "date"}),
			"due_at": forms.DateInput(attrs={"type": "date"}),
			"notes": forms.Textarea(attrs={"rows": 3}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Hide raw VAT rate; derive it from the checkbox instead.
		if "vat_rate" in self.fields:
			self.fields["vat_rate"].widget = forms.HiddenInput()
			self.fields["vat_rate"].required = False
		# Set initial state of the checkbox based on existing invoice rate.
		instance = getattr(self, "instance", None)
		if instance and getattr(instance, "vat_rate", None) is not None:
			self.fields["apply_vat"].initial = bool(instance.vat_rate and instance.vat_rate > Decimal("0.00"))
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")

	def clean(self):
		"""Invoice validation rules."""
		cleaned = super().clean()
		issued_at = cleaned.get("issued_at")
		due_at = cleaned.get("due_at")

		if issued_at and due_at and due_at < issued_at:
			self.add_error("due_at", "Due date cannot be earlier than issued date.")

		# Set VAT rate based on the checkbox: 18% when checked, 0% otherwise.
		apply_vat = bool(cleaned.get("apply_vat"))
		cleaned["vat_rate"] = Decimal("0.18") if apply_vat else Decimal("0.00")

		return cleaned


class InvoiceItemForm(forms.ModelForm):
	class Meta:
		model = InvoiceItem
		exclude = ["invoice"]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# If a product is selected, we can derive description + price.
		if "unit_cost" in self.fields:
			self.fields["unit_cost"].required = False
			self.fields["unit_cost"].widget = forms.HiddenInput()
		if "unit_price" in self.fields:
			self.fields["unit_price"].required = False
		if "description" in self.fields:
			self.fields["description"].required = False
		# Keep numeric inputs clean (no pre-filled 0.00 / 1.00 on create).
		if not self.is_bound and not getattr(self.instance, "pk", None):
			for name in ("quantity", "unit_price"):
				if name in self.fields:
					self.fields[name].initial = ""
					self.fields[name].widget.attrs.setdefault("placeholder", "")
		for name in ("quantity", "unit_price"):
			if name in self.fields:
				self.fields[name].widget.attrs.setdefault("step", "0.01")
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")

	def clean(self):
		cleaned = super().clean()
		product = cleaned.get("product")
		service = cleaned.get("service")
		description = (cleaned.get("description") or "").strip()
		unit_cost = cleaned.get("unit_cost")
		unit_price = cleaned.get("unit_price")
		if product and service:
			self.add_error("service", "Please choose either a product or a service, not both.")
			return cleaned

		# Preserve unit_cost on edit if it was not posted.
		if unit_cost is None and getattr(self.instance, "pk", None):
			cleaned["unit_cost"] = getattr(self.instance, "unit_cost", None)
			unit_cost = cleaned.get("unit_cost")

		if product:
			if not description:
				prod_desc = (getattr(product, "description", "") or "").strip()
				cleaned["description"] = f"{product.name} — {prod_desc}" if prod_desc else product.name
			# Snapshot cost for profit reporting.
			cleaned["unit_cost"] = getattr(product, "cost_price", None)
			if unit_price is None:
				cleaned["unit_price"] = product.unit_price
		elif service:
			# Services use service_charge for cost; keep unit_cost at 0 for clarity.
			cleaned["unit_cost"] = Decimal("0.00")
		if service:
			if not description:
				s_desc = (getattr(service, "description", "") or "").strip()
				cleaned["description"] = f"{service.name} — {s_desc}" if s_desc else service.name
			if unit_price is None:
				cleaned["unit_price"] = service.unit_price
		if not (cleaned.get("description") or "").strip():
			self.add_error("description", "Please enter a description for this line.")
		# If product is not selected, unit price must be provided.
		if not product and not service and cleaned.get("unit_price") is None:
			self.add_error("unit_price", "Please enter a unit price.")
		return cleaned


class InvoiceSignatureForm(forms.Form):
	name = forms.CharField(max_length=120, required=False)

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["name"].widget.attrs.setdefault("class", "form-control")


class PaymentForm(forms.ModelForm):
	"""Record a payment against an invoice (supports partial and full payments)."""

	class Meta:
		model = Payment
		exclude = ["invoice", "receipt_number", "recorded_by", "created_at"]
		widgets = {
			"paid_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
			"notes": forms.Textarea(attrs={"rows": 2}),
		}

	def __init__(self, *args, invoice: Invoice, **kwargs):
		self.invoice = invoice
		super().__init__(*args, **kwargs)
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")
		# Payments are recorded in whole currency units; guide the browser input.
		if "amount" in self.fields:
			self.fields["amount"].widget.attrs.setdefault("step", "1")

	def clean_amount(self):
		amount = self.cleaned_data.get("amount")
		if amount is None:
			return amount
		if amount <= Decimal("0.00"):
			raise forms.ValidationError("Amount must be greater than 0.")
		# Enforce whole currency units (no cents on entry).
		if amount != amount.to_integral_value():
			raise forms.ValidationError("Please enter whole amounts only (e.g. 100000, not 100000.50).")

		# Avoid accidental over-payment.
		outstanding = self.invoice.outstanding_balance()
		if outstanding > Decimal("0.00") and amount > outstanding:
			raise forms.ValidationError(f"Amount cannot exceed outstanding balance ({outstanding}).")
		return amount

	def clean(self):
		cleaned = super().clean()
		method = cleaned.get("method")
		method_other = (cleaned.get("method_other") or "").strip()

		if method == Payment.Method.OTHER:
			if not method_other:
				self.add_error("method_other", "Please specify the payment method.")
			else:
				cleaned["method_other"] = method_other
		else:
			cleaned["method_other"] = ""

		return cleaned

	def save(self, commit=True):
		obj: Payment = super().save(commit=False)
		obj.invoice = self.invoice
		if commit:
			obj.save()
		return obj


class PaymentRefundForm(forms.ModelForm):
	"""Record a refund against a specific payment (admin-only in views)."""

	class Meta:
		model = PaymentRefund
		exclude = ["payment", "invoice", "refunded_by", "created_at"]
		widgets = {
			"refunded_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
			"notes": forms.Textarea(attrs={"rows": 2}),
		}

	def __init__(self, *args, payment: Payment, **kwargs):
		self.payment = payment
		super().__init__(*args, **kwargs)
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")
		# Match payment input style
		if "amount" in self.fields:
			self.fields["amount"].widget.attrs.setdefault("step", "1")

	def clean_amount(self):
		amount = self.cleaned_data.get("amount")
		if amount is None:
			return amount
		if amount <= Decimal("0.00"):
			raise forms.ValidationError("Refund amount must be greater than 0.")
		# Whole currency units for consistency with payment entry.
		if amount != amount.to_integral_value():
			raise forms.ValidationError("Please enter whole amounts only (e.g. 100000, not 100000.50).")

		already_refunded = sum((r.amount for r in self.payment.refunds.all()), Decimal("0.00"))
		refundable = (self.payment.amount or Decimal("0.00")) - already_refunded
		if refundable < Decimal("0.00"):
			refundable = Decimal("0.00")
		if amount > refundable:
			raise forms.ValidationError(f"Refund cannot exceed refundable amount ({refundable}).")
		return amount

	def clean(self):
		cleaned = super().clean()
		# Policy: refunds can only be made within 21 days of the payment date.
		# Enforce based on current time to prevent backdating.
		try:
			deadline = self.payment.refund_deadline
		except Exception:
			deadline = None

		if deadline is not None and timezone.now() > deadline:
			deadline_local = timezone.localtime(deadline)
			raise forms.ValidationError(
				f"Refund window expired. Refunds are allowed within 21 days of payment date (deadline: {deadline_local:%Y-%m-%d %H:%M})."
			)
		return cleaned

	def save(self, commit=True):
		obj: PaymentRefund = super().save(commit=False)
		obj.payment = self.payment
		obj.invoice = self.payment.invoice
		if commit:
			obj.save()
		return obj
