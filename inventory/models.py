from decimal import Decimal
import uuid

from django.db import models, transaction
from django.utils import timezone


class Supplier(models.Model):
	name = models.CharField(max_length=255, unique=True)
	contact_person = models.CharField(max_length=255, blank=True, default="")
	phone = models.CharField(max_length=50, blank=True)
	alt_phone = models.CharField(max_length=50, blank=True, default="")
	email = models.EmailField(blank=True)
	website = models.CharField(max_length=255, blank=True, default="")
	address = models.CharField(max_length=255, blank=True)
	tin = models.CharField(max_length=80, blank=True, default="")
	notes = models.TextField(blank=True, default="")
	is_active = models.BooleanField(default=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name


class SupplierProductPrice(models.Model):
	"""Captures what a supplier offers and at what rate.

	Can be linked to an inventory Product for stock items, or just use
	`item_name` for simple free-text supplies (independent supplies module).
	"""

	supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="product_prices")
	product = models.ForeignKey(
		"inventory.Product",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="supplier_prices",
	)
	# Free-text description of what they supply (used when no Product is linked).
	item_name = models.CharField(max_length=255, blank=True, default="")
	# Human unit label for this price, e.g. "kg", "meter", "box".
	quantity_unit = models.CharField(max_length=40, blank=True, default="")
	currency = models.CharField(max_length=10, default="UGX")
	unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
	# Minimum order quantity for this price break (optional).
	min_order_quantity = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
	# Optional lead time for this specific supply in days.
	lead_time_days = models.PositiveIntegerField(null=True, blank=True)
	quoted_at = models.DateField(default=timezone.localdate)
	notes = models.TextField(blank=True, default="")
	is_active = models.BooleanField(default=True)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-quoted_at", "-id"]
		indexes = [
			models.Index(fields=["product", "supplier", "-quoted_at"]),
		]

	def __str__(self):
		label = self.item_name or (str(self.product) if self.product_id else "-")
		return f"{self.supplier} - {label} @ {self.unit_price} {self.currency}"


class ProductCategory(models.Model):
	class CategoryType(models.TextChoices):
		ITPRODUCT = "itproduct", "IT PRODUCTS"
		PRINTING_MATERIAL = "printing_material", "PRINTING MATERIAL"
		BRANDING_MATERIAL = "branding_material", "BRANDING MATERIAL"
		PROMOTIONAL_MATERIAL = "promotional_material", "PROMOTIONAL MATERIAL"
		MACHINERY = "machinery", "MACHINERY"
		STATIONERY = "stationery", "STATIONERY"
		PPE = "ppe", "PPE"
		GENERAL = "general", "GENERAL"
		OTHER = "other", "OTHER"

	name = models.CharField(max_length=120, unique=True)
	category_type = models.CharField(max_length=20, choices=CategoryType.choices)

	def __str__(self):
		return self.name


class ProductSequence(models.Model):
	year = models.PositiveIntegerField(unique=True)
	last_number = models.PositiveIntegerField(default=0)


class Product(models.Model):
	branch = models.ForeignKey(
		"core.Branch",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="products",
	)

	sku = models.CharField(max_length=60, unique=True, blank=True)
	name = models.CharField(max_length=255)
	description = models.TextField(blank=True, default="")
	category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name="products")
	supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")

	unit = models.CharField(max_length=40, default="pcs")
	# Sales price.
	unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Price")
	# Cost price (COGS per unit). Used for gross profit reporting.
	cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Cost price")
	vat_exempt = models.BooleanField(default=False)

	stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Quantity")
	low_stock_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Reorder level")

	is_active = models.BooleanField(default=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	@property
	def is_low_stock(self) -> bool:
		return self.stock_quantity <= self.low_stock_threshold

	@property
	def reorder_level(self):
		return self.low_stock_threshold

	@property
	def profit_per_unit(self) -> Decimal:
		return ((self.unit_price or Decimal("0.00")) - (self.cost_price or Decimal("0.00"))).quantize(Decimal("0.01"))

	def __str__(self):
		return f"{self.sku} - {self.name}"

	def _next_sku(self) -> str:
		year = timezone.localdate().year
		with transaction.atomic():
			seq, _ = ProductSequence.objects.select_for_update().get_or_create(year=year)
			seq.last_number += 1
			seq.save(update_fields=["last_number"])
			return f"SKU-{year}-{seq.last_number:05d}"

	def save(self, *args, **kwargs):
		if not (self.sku or "").strip():
			try:
				self.sku = self._next_sku()
			except Exception:
				# Fallback that stays unique even if sequence locking isn't available.
				stamp = timezone.now().strftime("%Y%m%d%H%M%S")
				self.sku = f"SKU-{stamp}-{uuid.uuid4().hex[:6].upper()}"
		super().save(*args, **kwargs)


class StockMovement(models.Model):
	class MovementType(models.TextChoices):
		IN = "in", "Stock In"
		OUT = "out", "Stock Out"

	product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock_movements")
	movement_type = models.CharField(max_length=10, choices=MovementType.choices)
	quantity = models.DecimalField(max_digits=12, decimal_places=2)
	reference = models.CharField(max_length=120, blank=True)
	notes = models.TextField(blank=True)
	occurred_at = models.DateTimeField(default=timezone.now)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-occurred_at", "-id"]

	def __str__(self):
		return f"{self.product.sku} {self.movement_type} {self.quantity}"
