from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

	dependencies = [
		("invoices", "0010_invoiceitem_unit_cost"),
		migrations.swappable_dependency(settings.AUTH_USER_MODEL),
	]

	operations = [
		migrations.AddField(
			model_name="invoice",
			name="cancel_reason",
			field=models.TextField(blank=True, default=""),
		),
		migrations.AddField(
			model_name="invoice",
			name="cancelled_at",
			field=models.DateTimeField(blank=True, null=True),
		),
		migrations.AddField(
			model_name="invoice",
			name="cancelled_by",
			field=models.ForeignKey(
				blank=True,
				null=True,
				on_delete=django.db.models.deletion.SET_NULL,
				related_name="cancelled_invoices",
				to=settings.AUTH_USER_MODEL,
			),
		),
	]
