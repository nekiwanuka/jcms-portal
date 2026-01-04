from django.db import migrations


def normalize_it_products(apps, schema_editor):
	ProductCategory = apps.get_model("inventory", "ProductCategory")

	# Fix any bad category_type values from earlier seeds
	ProductCategory.objects.filter(category_type="IT PRODUCT").update(category_type="itproduct")
	ProductCategory.objects.filter(category_type="IT PRODUCTS").update(category_type="itproduct")

	# Rename specific category names as requested
	ProductCategory.objects.filter(name="ITPRODUCTS").update(name="IT PRODUCTS", category_type="itproduct")
	ProductCategory.objects.filter(name="ITproducts").update(name="IT products", category_type="itproduct")

	# Common legacy name (optional cleanup)
	ProductCategory.objects.filter(name="IT PRODUCT").update(name="IT PRODUCTS", category_type="itproduct")
	ProductCategory.objects.filter(name="ITPRODUCT").update(name="IT products", category_type="itproduct")


class Migration(migrations.Migration):

	dependencies = [
		("inventory", "0012_alter_productcategory_category_type"),
	]

	operations = [
		migrations.RunPython(normalize_it_products, migrations.RunPython.noop),
	]
