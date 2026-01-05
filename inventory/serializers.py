from rest_framework import serializers

from .models import Product, ProductCategory, StockMovement, Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "email", "address", "is_active", "created_at", "updated_at"]


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name", "category_type"]


class ProductSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "branch",
            "sku",
            "name",
            "description",
            "category",
            "supplier",
            "unit",
            "unit_price",
            "cost_price",
            "stock_quantity",
            "low_stock_threshold",
            "is_low_stock",
            "is_active",
            "created_at",
            "updated_at",
        ]


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = [
            "id",
            "product",
            "movement_type",
            "quantity",
            "reference",
            "notes",
            "occurred_at",
            "created_at",
        ]
