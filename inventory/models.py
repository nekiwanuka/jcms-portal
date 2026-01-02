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
	"""Captures supplier pricing per product for comparison."""

	supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="product_prices")
	product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE, related_name="supplier_prices")
	currency = models.CharField(max_length=10, default="UGX")
	unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
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
		return f"{self.supplier} - {self.product} @ {self.unit_price} {self.currency}"


class ProductCategory(models.Model):
	class CategoryType(models.TextChoices):
		PRINTING = "printing", "Printing"
		IT = "it", "IT"
		MEDICAL = "medical", "Medical"
		PPE = "ppe", "PPE"

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
	category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name="products")
	supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")

	unit = models.CharField(max_length=40, default="pcs")
	unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

	stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
	low_stock_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

	is_active = models.BooleanField(default=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	@property
	def is_low_stock(self) -> bool:
		return self.stock_quantity <= self.low_stock_threshold

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
