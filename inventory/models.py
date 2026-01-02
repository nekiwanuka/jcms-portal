from decimal import Decimal

from django.db import models
from django.utils import timezone


class Supplier(models.Model):
	name = models.CharField(max_length=255, unique=True)
	phone = models.CharField(max_length=50, blank=True)
	email = models.EmailField(blank=True)
	address = models.CharField(max_length=255, blank=True)
	is_active = models.BooleanField(default=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name


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


class Product(models.Model):
	branch = models.ForeignKey(
		"core.Branch",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="products",
	)

	sku = models.CharField(max_length=60, unique=True)
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
