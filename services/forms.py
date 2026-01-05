from decimal import Decimal

from django import forms

from .models import Service, ServiceCategory


class ServiceForm(forms.ModelForm):
	"""Service create/edit form.

	Sales price is what invoices/quotations pick.
	Service charge is internal cost; Profit is derived automatically.
	"""

	class Meta:
		model = Service
		fields = [
			"branch",
			"category",
			"name",
			"description",
			"unit_price",
			"service_charge",
			"profit_amount",
			"is_active",
		]
		widgets = {
			"description": forms.Textarea(attrs={"rows": 3}),
		}
		labels = {
			"unit_price": "Sales price",
			"description": "Details",
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Profit is computed; show it but don't require user input.
		if "profit_amount" in self.fields:
			self.fields["profit_amount"].required = False
			self.fields["profit_amount"].widget.attrs.setdefault("readonly", True)
			self.fields["profit_amount"].help_text = "Auto-calculated as Sales price − Service charge."

		# Allow category to be optional; encourage later categorization.
		if "category" in self.fields:
			self.fields["category"].required = False
			self.fields["category"].empty_label = "(Optional) Select category"

		for name in ("unit_price", "service_charge", "profit_amount"):
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
		sales = cleaned.get("unit_price")
		charge = cleaned.get("service_charge")
		if sales is not None and sales < 0:
			self.add_error("unit_price", "Sales price cannot be negative.")
		if charge is not None and charge < 0:
			self.add_error("service_charge", "Service charge cannot be negative.")

		# Ensure profit field matches derived amount even though it's readonly.
		try:
			sales_v = (sales or Decimal("0.00")).quantize(Decimal("0.01"))
			charge_v = (charge or Decimal("0.00")).quantize(Decimal("0.01"))
			cleaned["profit_amount"] = (sales_v - charge_v).quantize(Decimal("0.01"))
		except Exception:
			pass
		return cleaned


class ServiceCategoryForm(forms.ModelForm):
	class Meta:
		model = ServiceCategory
		fields = ["name", "is_active"]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			else:
				widget.attrs.setdefault("class", "form-control")
