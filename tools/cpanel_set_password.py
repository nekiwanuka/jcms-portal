"""cPanel password reset helper.

Use this when you can open the site but login says "Invalid credentials".

How to run (recommended):
1) In cPanel Setup Python App, add Environment Variables:
   - TARGET_EMAIL=admin@example.com
   - NEW_PASSWORD=your-new-password
2) Execute this script.
3) Remove NEW_PASSWORD from env vars afterward.

This script does NOT print the password.
"""

import os

TARGET_EMAIL = (os.environ.get("TARGET_EMAIL") or "").strip().lower()
NEW_PASSWORD = os.environ.get("NEW_PASSWORD") or ""

if not TARGET_EMAIL or not NEW_PASSWORD:
	raise SystemExit(
		"Missing env vars. Set TARGET_EMAIL and NEW_PASSWORD in your environment variables, then re-run."
	)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jambas.settings")

import django  # noqa: E402

django.setup()

from accounts.models import User  # noqa: E402

try:
	user = User.objects.get(email=TARGET_EMAIL)
except User.DoesNotExist:
	raise SystemExit(f"No user found with email={TARGET_EMAIL}. Run tools/cpanel_diag.py to confirm DB + users.")

user.set_password(NEW_PASSWORD)
user.save(update_fields=["password"])

print(f"Password updated for {TARGET_EMAIL} (user id={user.id}).")
