from decimal import Decimal

from django import forms
from django.db import transaction
from django.db.models import F
from django.forms import inlineformset_factory

from .models import Product, ProductCategory, StockMovement, Supplier, SupplierProductPrice


class ProductCategoryForm(forms.ModelForm):
	class Meta:
		model = ProductCategory
		fields = ["name", "category_type"]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Default new categories to OTHER unless user chooses.
		if not self.instance.pk and "category_type" in self.fields:
			self.fields["category_type"].initial = ProductCategory.CategoryType.OTHER
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")


class ProductForm(forms.ModelForm):
	"""Product create/edit form.

	Uses Bootstrap-friendly widgets.
	"""

	category_name = forms.CharField(
		required=False,
		label="Category (manual)",
		help_text="Optional. If you choose OTHER (or leave Category blank), type the category name here.",
	)

	class Meta:
		model = Product
		fields = "__all__"

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if "sku" in self.fields:
			self.fields["sku"].required = False
		if "category" in self.fields:
			# Allow manual category creation.
			self.fields["category"].required = False
			self.fields["category"].empty_label = "(Optional) Select category"
		if "stock_quantity" in self.fields:
			self.fields["stock_quantity"].help_text = "Stock level: number of units currently in stock (Quantity)."
		if "low_stock_threshold" in self.fields:
			self.fields["low_stock_threshold"].help_text = "Reorder level: when Quantity is at/below this, product is Low stock."
		if "category_name" in self.fields:
			self.fields["category_name"].widget.attrs.setdefault("placeholder", "e.g. IT PRODUCTS, MACHINERY, or a custom category")
		# Helpful numeric input hints
		for name in ("unit_price", "cost_price", "stock_quantity", "low_stock_threshold"):
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
		cost_price = cleaned.get("cost_price")
		stock_quantity = cleaned.get("stock_quantity")
		low_stock_threshold = cleaned.get("low_stock_threshold")
		category = cleaned.get("category")
		category_name = (cleaned.get("category_name") or "").strip()

		if unit_price is not None and unit_price < 0:
			self.add_error("unit_price", "Unit price cannot be negative.")
		if cost_price is not None and cost_price < 0:
			self.add_error("cost_price", "Cost price cannot be negative.")
		if stock_quantity is not None and stock_quantity < 0:
			self.add_error("stock_quantity", "Stock quantity cannot be negative.")
		if low_stock_threshold is not None and low_stock_threshold < 0:
			self.add_error("low_stock_threshold", "Low stock threshold cannot be negative.")

		# Category rules:
		# - User can select a category from the list.
		# - Or leave it blank and type one manually.
		# - If they select OTHER, manual name is required.
		if category is None:
			if not category_name:
				self.add_error("category", "Select a category or enter one manually.")
			else:
				# Match to standard categories if it exactly matches one; otherwise store as OTHER.
				key = category_name.strip()
				# Exact requested normalizations
				if key == "ITproducts":
					category_type, canonical_name = (ProductCategory.CategoryType.ITPRODUCT, "IT products")
				else:
					key_upper = key.upper()
					standard_map = {
						"ITPRODUCTS": (ProductCategory.CategoryType.ITPRODUCT, "IT PRODUCTS"),
						"IT PRODUCTS": (ProductCategory.CategoryType.ITPRODUCT, "IT PRODUCTS"),
						"ITPRODUCT": (ProductCategory.CategoryType.ITPRODUCT, "IT products"),
						"IT PRODUCT": (ProductCategory.CategoryType.ITPRODUCT, "IT products"),
						"PRINTING MATERIAL": (ProductCategory.CategoryType.PRINTING_MATERIAL, "PRINTING MATERIAL"),
						"BRANDING MATERIAL": (ProductCategory.CategoryType.BRANDING_MATERIAL, "BRANDING MATERIAL"),
						"PROMOTIONAL MATERIAL": (ProductCategory.CategoryType.PROMOTIONAL_MATERIAL, "PROMOTIONAL MATERIAL"),
						"MACHINERY": (ProductCategory.CategoryType.MACHINERY, "MACHINERY"),
						"STATIONERY": (ProductCategory.CategoryType.STATIONERY, "STATIONERY"),
						"PPE": (ProductCategory.CategoryType.PPE, "PPE"),
						"GENERAL": (ProductCategory.CategoryType.GENERAL, "GENERAL"),
						"OTHER": (ProductCategory.CategoryType.OTHER, "OTHER"),
					}
					category_type, canonical_name = standard_map.get(key_upper, (ProductCategory.CategoryType.OTHER, category_name))
				obj, _ = ProductCategory.objects.get_or_create(
					name=canonical_name,
					defaults={"category_type": category_type},
				)
				# Keep the type aligned if user manually enters a standard category name.
				if obj.category_type != category_type:
					ProductCategory.objects.filter(pk=obj.pk).update(category_type=category_type)
					obj.category_type = category_type
				cleaned["category"] = obj
		else:
			# If user selected the generic "OTHER" category, require a manual name and convert
			# to a specific category row. Do not force manual entry for already-specific
			# custom categories that happen to have category_type=OTHER.
			is_generic_other = (
				getattr(category, "category_type", None) == ProductCategory.CategoryType.OTHER
				and (getattr(category, "name", "") or "").strip().upper() == "OTHER"
			)
			if is_generic_other:
				if not category_name:
					self.add_error("category_name", "Please type the category name for OTHER.")
				else:
					obj, _ = ProductCategory.objects.get_or_create(
						name=category_name,
						defaults={"category_type": ProductCategory.CategoryType.OTHER},
					)
					cleaned["category"] = obj

		return cleaned


class SupplierForm(forms.ModelForm):
	class Meta:
		model = Supplier
		fields = "__all__"

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


class SupplierProductPriceForm(forms.ModelForm):
	class Meta:
		model = SupplierProductPrice
		fields = [
			"supplier",
			"product",
			"item_name",
			"quantity_unit",
			"currency",
			"unit_price",
			"min_order_quantity",
			"lead_time_days",
			"quoted_at",
			"is_active",
			"notes",
		]
		widgets = {
			"quoted_at": forms.DateInput(attrs={"type": "date"}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Friendlier dropdowns/placeholders for the supplies UX
		if "supplier" in self.fields:
			self.fields["supplier"].empty_label = "Select supplier"
		if "product" in self.fields:
			self.fields["product"].required = False
			self.fields["product"].empty_label = "(Optional) Link to product"
		if "item_name" in self.fields:
			self.fields["item_name"].widget.attrs.setdefault("placeholder", "e.g. Photo printing A4")
		if "quantity_unit" in self.fields:
			self.fields["quantity_unit"].widget.attrs.setdefault("placeholder", "e.g. kg, meter, box")
		if "min_order_quantity" in self.fields:
			self.fields["min_order_quantity"].widget.attrs.setdefault("placeholder", "e.g. 10")
		if "unit_price" in self.fields:
			field = self.fields["unit_price"]
			# Use text input so our JS formatter can apply commas/decimals
			# without fighting the browser's numeric validation.
			field.widget = forms.TextInput(attrs=field.widget.attrs)
			field.widget.attrs.setdefault("data-money-input", "1")
		if "lead_time_days" in self.fields:
			self.fields["lead_time_days"].widget.attrs.setdefault("placeholder", "e.g. 7")
		for name, field in self.fields.items():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select form-select-sm")
			else:
				widget.attrs.setdefault("class", "form-control form-control-sm")

	def clean(self):
		cleaned = super().clean()
		unit_price = cleaned.get("unit_price")
		product = cleaned.get("product")
		item_name = (cleaned.get("item_name") or "").strip()
		if not product and not item_name:
			self.add_error("product", "Select a product or enter what they supply.")
			self.add_error("item_name", "Enter what they supply if no product is selected.")
		elif product and not item_name:
			# Default the free-text name from the linked product for clarity.
			cleaned["item_name"] = product.name
		if unit_price is not None and unit_price < 0:
			self.add_error("unit_price", "Unit price cannot be negative.")
		return cleaned


class SupplierProductForSupplierForm(forms.ModelForm):
	"""Inline form for managing what a supplier supplies and at which rate.

	Used on the supplier edit screen so you can add multiple
	products and rates for a single supplier.
	"""

	class Meta:
		model = SupplierProductPrice
		fields = [
			"product",
			"item_name",
			"quantity_unit",
			"currency",
			"unit_price",
			"min_order_quantity",
			"lead_time_days",
			"quoted_at",
			"is_active",
			"notes",
		]
		widgets = {
			"quoted_at": forms.DateInput(attrs={"type": "date"}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if "product" in self.fields:
			self.fields["product"].required = False
			self.fields["product"].empty_label = "(Optional) Link to product"
		if "item_name" in self.fields:
			self.fields["item_name"].widget.attrs.setdefault("placeholder", "e.g. Printing papers A4")
		if "quantity_unit" in self.fields:
			self.fields["quantity_unit"].widget.attrs.setdefault("placeholder", "e.g. kg, meter, box")
		if "min_order_quantity" in self.fields:
			self.fields["min_order_quantity"].widget.attrs.setdefault("placeholder", "e.g. 10")
		if "unit_price" in self.fields:
			field = self.fields["unit_price"]
			field.widget = forms.TextInput(attrs=field.widget.attrs)
			field.widget.attrs.setdefault("data-money-input", "1")
		if "lead_time_days" in self.fields:
			self.fields["lead_time_days"].widget.attrs.setdefault("placeholder", "Days")
		for name, field in self.fields.items():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select form-select-sm")
			else:
				widget.attrs.setdefault("class", "form-control form-control-sm")

	def clean(self):
		cleaned = super().clean()
		product = cleaned.get("product")
		item_name = (cleaned.get("item_name") or "").strip()
		if not product and not item_name:
			self.add_error("product", "Select a product or enter what they supply.")
			self.add_error("item_name", "Enter what they supply if no product is selected.")
		elif product and not item_name:
			cleaned["item_name"] = product.name
		return cleaned


SupplierProductPriceFormSet = inlineformset_factory(
	Supplier,
	SupplierProductPrice,
	form=SupplierProductForSupplierForm,
	extra=3,
	can_delete=True,
)


class StockMovementAdjustForm(forms.ModelForm):
	"""Create a stock movement and update Product.stock_quantity accordingly."""

	class Meta:
		model = StockMovement
		fields = ["movement_type", "quantity", "reference", "occurred_at", "notes"]
		widgets = {
			"occurred_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
			"notes": forms.Textarea(attrs={"rows": 2}),
		}

	def __init__(self, *args, product: Product, **kwargs):
		self.product = product
		super().__init__(*args, **kwargs)
		if "quantity" in self.fields:
			self.fields["quantity"].widget.attrs.setdefault("step", "0.01")
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")

	def clean_quantity(self):
		qty = self.cleaned_data.get("quantity")
		if qty is None:
			return qty
		if qty <= Decimal("0.00"):
			raise forms.ValidationError("Quantity must be greater than 0.")
		return qty

	def save(self, commit=True):
		obj: StockMovement = super().save(commit=False)
		obj.product = self.product
		qty = obj.quantity
		with transaction.atomic():
			# Apply stock change first.
			if obj.movement_type == StockMovement.MovementType.IN:
				Product.objects.filter(pk=self.product.pk).update(stock_quantity=F("stock_quantity") + qty)
			else:
				Product.objects.filter(pk=self.product.pk).update(stock_quantity=F("stock_quantity") - qty)
			if commit:
				obj.save()
		return obj
