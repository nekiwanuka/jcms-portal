from __future__ import annotations

from django.conf import settings
from django.shortcuts import render


class HideDebug404Middleware:
	"""Hide Django's technical 404 page (which lists URL patterns) when DEBUG=True.

	Django's debug 404 can expose internal URL structure. This middleware replaces
	the HTML 404 response with a generic template.
	"""

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		response = self.get_response(request)
		if settings.DEBUG and getattr(response, "status_code", None) == 404:
			content_type = (response.get("Content-Type") or "").lower()
			# Only override HTML pages; keep JSON/API 404 responses intact.
			if content_type.startswith("text/html"):
				return render(request, "404.html", status=404)
		return response
