from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
	dependencies = [
		("invoices", "0004_payment_method_other"),
		("documents", "0003_document_doc_type_other"),
	]

	operations = [
		migrations.AddField(
			model_name="document",
			name="related_invoice",
			field=models.ForeignKey(
				blank=True,
				null=True,
				on_delete=django.db.models.deletion.SET_NULL,
				related_name="documents",
				to="invoices.invoice",
			),
		),
		migrations.AddField(
			model_name="document",
			name="related_payment",
			field=models.ForeignKey(
				blank=True,
				null=True,
				on_delete=django.db.models.deletion.SET_NULL,
				related_name="documents",
				to="invoices.payment",
			),
		),
	]
