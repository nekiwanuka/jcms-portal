from django.contrib import admin

from .models import Product, ProductCategory, StockMovement, Supplier, SupplierProductPrice


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
	list_display = ("name", "phone", "email", "is_active")
	list_filter = ("is_active",)
	search_fields = ("name", "phone", "email")


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
	list_display = ("name", "category_type")
	list_filter = ("category_type",)
	search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
	list_display = ("sku", "name", "category", "unit_price", "cost_price", "stock_quantity", "low_stock_threshold", "is_active")
	list_filter = ("category", "is_active")
	search_fields = ("sku", "name")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
	list_display = ("product", "movement_type", "quantity", "reference", "occurred_at")
	list_filter = ("movement_type",)
	search_fields = ("product__sku", "product__name", "reference")


@admin.register(SupplierProductPrice)
class SupplierProductPriceAdmin(admin.ModelAdmin):
	list_display = ("supplier", "product", "unit_price", "currency", "quoted_at", "is_active")
	list_filter = ("currency", "is_active", "quoted_at")
	search_fields = ("supplier__name", "product__sku", "product__name")
