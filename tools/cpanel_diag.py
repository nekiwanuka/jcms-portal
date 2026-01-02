"""cPanel diagnostic helper.

Run this from cPanel "Setup Python App" -> Execute Python Script.
It prints database + static configuration and a quick user summary.

Safe output: does NOT print passwords or secrets.
"""

import os
import sys
from pathlib import Path

# Ensure project root is on sys.path (cPanel can run scripts with sys.path[0]=tools/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jambas.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

try:
	from accounts.models import User  # noqa: E402
except Exception as e:
	User = None
	_import_err = e


def _fmt(v):
	return "<empty>" if v in (None, "") else str(v)


print("=== JCMS / Django diagnostic ===")
print(f"DEBUG={getattr(settings, 'DEBUG', None)}")
print(f"ALLOWED_HOSTS={getattr(settings, 'ALLOWED_HOSTS', None)}")

print("\n--- Database ---")
db = settings.DATABASES.get("default", {})
print(f"ENGINE={_fmt(db.get('ENGINE'))}")
print(f"NAME={_fmt(db.get('NAME'))}")
print(f"HOST={_fmt(db.get('HOST'))}")
print(f"PORT={_fmt(db.get('PORT'))}")
print(f"USER={_fmt(db.get('USER'))}")

print("\n--- Static/Media ---")
print(f"STATIC_URL={_fmt(getattr(settings, 'STATIC_URL', None))}")
print(f"STATIC_ROOT={_fmt(getattr(settings, 'STATIC_ROOT', None))}")
print(f"MEDIA_URL={_fmt(getattr(settings, 'MEDIA_URL', None))}")
print(f"MEDIA_ROOT={_fmt(getattr(settings, 'MEDIA_ROOT', None))}")

static_root = getattr(settings, "STATIC_ROOT", None)
if static_root:
	candidate_svg = os.path.join(str(static_root), "images", "jambas-logo-white.svg")
	candidate_png = os.path.join(str(static_root), "images", "jambas-company-logo.png")
	print("\n--- Static files existence (after collectstatic) ---")
	print(f"SVG exists? {os.path.exists(candidate_svg)} | {candidate_svg}")
	print(f"PNG exists? {os.path.exists(candidate_png)} | {candidate_png}")
else:
	print("\nSTATIC_ROOT is not set; cannot check collected static files.")

print("\n--- Users ---")
if User is None:
	print(f"Could not import accounts.User: {_import_err}")
else:
	qs = User.objects.all().order_by("id")
	print(f"User count: {qs.count()}")
	for u in qs[:10]:
		print(
			f"- id={u.id} email={u.email} active={u.is_active} staff={u.is_staff} superuser={u.is_superuser} role={getattr(u,'role',None)}"
		)
