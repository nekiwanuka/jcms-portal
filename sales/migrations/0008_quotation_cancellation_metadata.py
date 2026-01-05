from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

	dependencies = [
		("sales", "0007_quotationitem_service"),
		migrations.swappable_dependency(settings.AUTH_USER_MODEL),
	]

	operations = [
		migrations.AddField(
			model_name="quotation",
			name="cancel_reason",
			field=models.TextField(blank=True, default=""),
		),
		migrations.AddField(
			model_name="quotation",
			name="cancelled_at",
			field=models.DateTimeField(blank=True, null=True),
		),
		migrations.AddField(
			model_name="quotation",
			name="cancelled_by",
			field=models.ForeignKey(
				blank=True,
				null=True,
				on_delete=django.db.models.deletion.SET_NULL,
				related_name="cancelled_quotations",
				to=settings.AUTH_USER_MODEL,
			),
		),
	]
