from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		("inventory", "0013_normalize_it_products_names"),
	]

	operations = [
		migrations.AlterField(
			model_name="productcategory",
			name="category_type",
			field=models.CharField(
				choices=[
					("itproduct", "IT PRODUCTS"),
					("printing_material", "PRINTING MATERIAL"),
					("branding_material", "BRANDING MATERIAL"),
					("promotional_material", "PROMOTIONAL MATERIAL"),
					("machinery", "MACHINERY"),
					("stationery", "STATIONERY"),
					("ppe", "PPE"),
					("general", "GENERAL"),
					("other", "OTHER"),
				],
				max_length=20,
			),
		),
	]
