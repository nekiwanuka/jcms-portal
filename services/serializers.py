from rest_framework import serializers

from .models import Service


class ServiceSerializer(serializers.ModelSerializer):
	sales_price = serializers.DecimalField(source="unit_price", max_digits=12, decimal_places=2, read_only=True)

	class Meta:
		model = Service
		fields = [
			"id",
			"branch",
			"category",
			"name",
			"description",
			"unit_price",
			"sales_price",
			"service_charge",
			"profit_amount",
			"is_active",
			"created_at",
			"updated_at",
		]
