from django.db import migrations, models


def forwards(apps, schema_editor):
	Bid = apps.get_model("bids", "Bid")
	# Map legacy status value 'awarded' -> 'won'
	Bid.objects.filter(status="awarded").update(status="won")


def backwards(apps, schema_editor):
	Bid = apps.get_model("bids", "Bid")
	Bid.objects.filter(status="won").update(status="awarded")


class Migration(migrations.Migration):
	dependencies = [
		("bids", "0003_bid_category_other"),
	]

	operations = [
		migrations.AddField(
			model_name="bid",
			name="submission_method",
			field=models.CharField(
				choices=[
					("email", "Email"),
					("portal", "Portal"),
					("physical", "Physical"),
					("other", "Other"),
				],
				default="email",
				max_length=20,
			),
		),
		migrations.AddField(
			model_name="bid",
			name="submission_method_other",
			field=models.CharField(blank=True, default="", max_length=120, verbose_name="Other (specify)"),
		),
		migrations.RunPython(forwards, backwards),
	]
