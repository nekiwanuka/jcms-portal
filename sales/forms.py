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
		# VAT: checkbox to enable/disable VAT; rate fixed at 18% when enabled.
		if "vat_enabled" in self.fields:
			self.fields["vat_enabled"].widget = forms.CheckboxInput()
			self.fields["vat_enabled"].required = False
			self.fields["vat_enabled"].label = "Apply VAT (18%)"
			self.fields["vat_enabled"].help_text = "Tick to apply 18% VAT; leave unticked for no VAT."
		if "vat_rate" in self.fields:
			# Hide the raw rate field; it is derived from the checkbox.
			self.fields["vat_rate"].widget = forms.HiddenInput()
			self.fields["vat_rate"].required = False
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
		# Derive VAT rate from the checkbox: 18% when enabled, 0% otherwise.
		enabled = bool(cleaned.get("vat_enabled"))
		cleaned["vat_enabled"] = enabled
		cleaned["vat_rate"] = Decimal("0.18") if enabled else Decimal("0.00")
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
		if "unit_price" in self.fields:
			self.fields["unit_price"].required = False
		# Make line entry clear: require a description/reason.
		if "description" in self.fields:
			# Let it be auto-filled from product; enforce in clean() for non-product lines.
			self.fields["description"].required = False
			self.fields["description"].label = "Description"
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
		item_name = (cleaned.get("item_name") or "").strip()
		description = (cleaned.get("description") or "").strip()
		unit_price = cleaned.get("unit_price")
		prod_desc = (getattr(product, "description", "") or "").strip() if product else ""
		svc_desc = (getattr(service, "description", "") or "").strip() if service else ""

		if product and service:
			self.add_error("service", "Please choose either a product or a service, not both.")
			return cleaned

		if product and not item_name:
			cleaned["item_name"] = product.name
			item_name = cleaned["item_name"]
		if product and not description:
			cleaned["description"] = f"{product.name} — {prod_desc}" if prod_desc else product.name
			description = cleaned["description"]
		if product and unit_price is None:
			cleaned["unit_price"] = product.unit_price
		if service and not item_name:
			cleaned["item_name"] = service.name
			item_name = cleaned["item_name"]
		if service and not description:
			cleaned["description"] = f"{service.name} — {svc_desc}" if svc_desc else service.name
			description = cleaned["description"]
		if service and unit_price is None:
			cleaned["unit_price"] = service.unit_price
		# If no product is selected, unit price must be provided.
		if not product and not service and cleaned.get("unit_price") is None:
			self.add_error("unit_price", "Please enter a unit price.")

		if not (product or service or item_name or description):
			self.add_error("item_name", "Select a product or enter item details.")
		if not description:
			self.add_error("description", "Please enter a description/reason for this line.")
		return cleaned
