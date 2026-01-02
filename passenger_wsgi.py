import os
import sys

# Ensure the project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jambas.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
