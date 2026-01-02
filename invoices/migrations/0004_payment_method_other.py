from django.db import migrations, models


class Migration(migrations.Migration):
	dependencies = [
		("invoices", "0003_invoice_prepared_by_name_invoice_signed_at_and_more"),
	]

	operations = [
		migrations.AddField(
			model_name="payment",
			name="method_other",
			field=models.CharField(blank=True, default="", max_length=120),
		),
	]
