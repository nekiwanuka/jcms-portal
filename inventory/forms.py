from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
	"""Product create/edit form.

	Uses Bootstrap-friendly widgets.
	"""

	class Meta:
		model = Product
		fields = "__all__"

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Helpful numeric input hints
		for name in ("unit_price", "stock_quantity", "low_stock_threshold"):
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
		"""Basic inventory validation."""
		cleaned = super().clean()
		unit_price = cleaned.get("unit_price")
		stock_quantity = cleaned.get("stock_quantity")
		low_stock_threshold = cleaned.get("low_stock_threshold")

		if unit_price is not None and unit_price < 0:
			self.add_error("unit_price", "Unit price cannot be negative.")
		if stock_quantity is not None and stock_quantity < 0:
			self.add_error("stock_quantity", "Stock quantity cannot be negative.")
		if low_stock_threshold is not None and low_stock_threshold < 0:
			self.add_error("low_stock_threshold", "Low stock threshold cannot be negative.")

		return cleaned
