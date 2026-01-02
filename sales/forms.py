from datetime import timedelta
from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import Quotation, QuotationItem


class QuotationForm(forms.ModelForm):
	class Meta:
		model = Quotation
		exclude = [
			"branch",
			"created_by",
			"number",
			"status",
			"subtotal_amount",
			"vat_amount_amount",
			"total_amount",
			"created_at",
			"updated_at",
		]
		widgets = {
			"valid_until": forms.DateInput(attrs={"type": "date"}),
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

		# Default validity: 14 days
		if not self.is_bound and not self.instance.pk and not self.initial.get("valid_until"):
			self.initial["valid_until"] = (timezone.localdate() + timedelta(days=14)).isoformat()

	def clean_discount_amount(self):
		discount = self.cleaned_data.get("discount_amount")
		if discount is None:
			return Decimal("0.00")
		if discount < Decimal("0.00"):
			raise forms.ValidationError("Discount cannot be negative.")
		return discount

	def clean_valid_until(self):
		valid_until = self.cleaned_data.get("valid_until")
		if valid_until and valid_until < timezone.localdate():
			raise forms.ValidationError("Validity date cannot be in the past.")
		return valid_until

	def clean(self):
		cleaned = super().clean()
		category = cleaned.get("category")
		category_other = (cleaned.get("category_other") or "").strip()
		if category == Quotation.Category.OTHER:
			if not category_other:
				self.add_error("category_other", "Please specify the 'Other' category.")
		else:
			cleaned["category_other"] = ""
		return cleaned


class QuotationItemForm(forms.ModelForm):
	class Meta:
		model = QuotationItem
		exclude = ["quotation", "total_price"]

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
