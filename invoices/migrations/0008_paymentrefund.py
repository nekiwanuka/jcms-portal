from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

	dependencies = [
		("invoices", "0007_invoice_stock_deducted_at"),
		migrations.swappable_dependency(settings.AUTH_USER_MODEL),
	]

	operations = [
		migrations.CreateModel(
			name="PaymentRefund",
			fields=[
				("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
				("amount", models.DecimalField(decimal_places=2, max_digits=12)),
				("refunded_at", models.DateTimeField(default=django.utils.timezone.now)),
				("reference", models.CharField(blank=True, default="", max_length=120)),
				("notes", models.TextField(blank=True, default="")),
				("created_at", models.DateTimeField(auto_now_add=True)),
				(
					"invoice",
					models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="refunds", to="invoices.invoice"),
				),
				(
					"payment",
					models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="refunds", to="invoices.payment"),
				),
				(
					"refunded_by",
					models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
				),
			],
			options={
				"ordering": ["-refunded_at", "-id"],
			},
		),
		migrations.AddIndex(
			model_name="paymentrefund",
			index=models.Index(fields=["invoice", "-refunded_at"], name="invoices_pa_invoice_61cc52_idx"),
		),
		migrations.AddIndex(
			model_name="paymentrefund",
			index=models.Index(fields=["payment", "-refunded_at"], name="invoices_pa_payment_d1987f_idx"),
		),
	]
