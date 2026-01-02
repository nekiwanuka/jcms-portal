from decimal import Decimal

from django import forms

from .models import Invoice, InvoiceItem, Payment


class InvoiceForm(forms.ModelForm):
	"""Invoice create/edit form.

	- `number` is auto-generated in the model, so it is excluded.
	- `created_by` is set in the view from the logged-in user.
	"""

	class Meta:
		model = Invoice
		exclude = ["number", "created_by", "created_at", "updated_at", "signed_by_name", "signed_at"]
		widgets = {
			"issued_at": forms.DateInput(attrs={"type": "date"}),
			"due_at": forms.DateInput(attrs={"type": "date"}),
			"notes": forms.Textarea(attrs={"rows": 3}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
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

		return cleaned


class InvoiceItemForm(forms.ModelForm):
	class Meta:
		model = InvoiceItem
		exclude = ["invoice"]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")


class InvoiceSignatureForm(forms.Form):
	name = forms.CharField(max_length=120)

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

	def clean_amount(self):
		amount = self.cleaned_data.get("amount")
		if amount is None:
			return amount
		if amount <= Decimal("0.00"):
			raise forms.ValidationError("Amount must be greater than 0.")

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
