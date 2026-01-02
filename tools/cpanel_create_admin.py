"""cPanel admin creation helper.

Use when:
- You cannot log in (invalid credentials)
- Forgot password isn't sending email (SMTP not configured yet)
- `createsuperuser` can't run (no TTY)

How to run (recommended):
1) In cPanel Setup Python App, add Environment Variables:
   - ADMIN_EMAIL=admin@yourdomain.com
   - ADMIN_PASSWORD=your-strong-password
2) Execute this script.
3) Remove ADMIN_PASSWORD env var afterward.

Safe output: does NOT print the password.
"""

import os

ADMIN_EMAIL = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or ""

if not ADMIN_EMAIL or not ADMIN_PASSWORD:
	raise SystemExit(
		"Missing env vars. Set ADMIN_EMAIL and ADMIN_PASSWORD in your environment variables, then re-run."
	)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jambas.settings")

import django  # noqa: E402

django.setup()

from accounts.models import User  # noqa: E402

user, created = User.objects.get_or_create(email=ADMIN_EMAIL, defaults={"is_active": True})
user.is_active = True
user.is_staff = True
user.is_superuser = True
try:
	user.role = User.Role.ADMIN
except Exception:
	# If roles change in the future, still ensure admin privileges.
	pass

user.set_password(ADMIN_PASSWORD)
user.save()

print(
	("Created" if created else "Updated")
	+ f" admin user {ADMIN_EMAIL} (id={user.id})."
)
