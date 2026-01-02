from django.db import migrations


def seed_product_categories(apps, schema_editor):
	ProductCategory = apps.get_model("inventory", "ProductCategory")

	# Ensure the UI has at least some categories to choose from.
	# These map directly to the built-in CategoryType choices.
	defaults = [
		("Printing", "printing"),
		("IT", "it"),
		("Medical", "medical"),
		("PPE", "ppe"),
	]

	for name, category_type in defaults:
		obj, created = ProductCategory.objects.get_or_create(
			name=name,
			defaults={"category_type": category_type},
		)
		if not created and getattr(obj, "category_type", None) != category_type:
			ProductCategory.objects.filter(pk=obj.pk).update(category_type=category_type)


class Migration(migrations.Migration):
	dependencies = [
		("inventory", "0002_supplier_alt_phone_supplier_contact_person_and_more"),
	]

	operations = [
		migrations.RunPython(seed_product_categories, migrations.RunPython.noop),
	]
