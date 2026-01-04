import os
import sys


def main() -> int:
	os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jambas.settings")
	# Ensure project root is on path
	sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

	import django

	django.setup()

	from django.contrib.auth import get_user_model
	from django.test import Client
	from django.urls import reverse

	from inventory.models import Product, ProductCategory

	User = get_user_model()

	admin = User.objects.filter(email="smoke_admin@example.com").first()
	if not admin:
		admin = User.objects.create_superuser(
			email="smoke_admin@example.com",
			password="pass",
			full_name="Smoke Admin",
		)
	admin.set_password("pass")
	admin.save(update_fields=["password"])

	user = User.objects.filter(email="smoke_user@example.com").first()
	if not user:
		user = User.objects.create_user(
			email="smoke_user@example.com",
			password="pass",
			full_name="Smoke User",
		)
	user.set_password("pass")
	user.save(update_fields=["password"])

	cat, _ = ProductCategory.objects.get_or_create(
		name="SMOKE",
		defaults={"category_type": ProductCategory.CategoryType.OTHER},
	)

	p, _ = Product.objects.get_or_create(
		sku="SMOKE-1",
		defaults={
			"name": "Smoke Product",
			"unit_price": 10,
			"stock_quantity": 5,
			"low_stock_threshold": 1,
			"category": cat,
			"is_active": True,
		},
	)
	Product.objects.filter(pk=p.pk).update(is_active=True)
	p.refresh_from_db()

	# Avoid DisallowedHost when ALLOWED_HOSTS is restrictive.
	# The Django test client defaults to HTTP_HOST='testserver'.
	# Pass an allowed host per-request.
	allowed_host = "localhost"

	# Non-admin: edit should load; delete should be rejected (redirect)
	c = Client()
	assert c.login(email="smoke_user@example.com", password="pass"), "Non-admin login failed"
	session = c.session
	session["otp_verified"] = True
	session.save()
	edit_resp = c.get(reverse("edit_inventory", args=[p.id]), HTTP_HOST=allowed_host)
	print("non_admin_edit_get", edit_resp.status_code)
	delete_resp = c.post(reverse("delete_inventory", args=[p.id]), HTTP_HOST=allowed_host)
	print("non_admin_delete_post", delete_resp.status_code)
	p.refresh_from_db()
	print("after_non_admin_delete_active", p.is_active)
	exists_after_non_admin = Product.objects.filter(pk=p.id).exists()

	# Admin: delete should succeed (delete or deactivate)
	c2 = Client()
	assert c2.login(email="smoke_admin@example.com", password="pass"), "Admin login failed"
	session2 = c2.session
	session2["otp_verified"] = True
	session2.save()
	delete_resp2 = c2.post(reverse("delete_inventory", args=[p.id]), HTTP_HOST=allowed_host)
	print("admin_delete_post", delete_resp2.status_code)
	print("exists_after_admin_delete", Product.objects.filter(pk=p.id).exists())

	non_admin_ok = (edit_resp.status_code == 200) and (delete_resp.status_code in {302, 303})
	# Non-admin delete must not delete the product.
	non_admin_ok = non_admin_ok and exists_after_non_admin

	admin_status_ok = delete_resp2.status_code in {302, 303}
	admin_deleted = Product.objects.filter(pk=p.id).exists() is False
	admin_deactivated = False
	if not admin_deleted and Product.objects.filter(pk=p.id).exists():
		p.refresh_from_db()
		admin_deactivated = p.is_active is False

	ok = non_admin_ok and admin_status_ok and (admin_deleted or admin_deactivated)

	print("smoke_ok", bool(ok))
	return 0 if ok else 1


if __name__ == "__main__":
	raise SystemExit(main())
