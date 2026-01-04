from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		("inventory", "0011_seed_product_categories_2026_01_04"),
	]

	operations = [
		migrations.AlterField(
			model_name="productcategory",
			name="category_type",
			field=models.CharField(
				choices=[
					("IT PRODUCT", "IT PRODUCT"),
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
