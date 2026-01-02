from django.conf import settings
from django.db import models


class Branch(models.Model):
	name = models.CharField(max_length=120, unique=True)
	code = models.CharField(max_length=20, unique=True)
	address = models.CharField(max_length=255, blank=True)
	phone = models.CharField(max_length=50, blank=True)
	is_active = models.BooleanField(default=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["name"]

	def __str__(self):
		return self.name


class AuditEvent(models.Model):
	"""Lightweight audit trail.

	Stores the *what/who/when* of key workflow actions without requiring admin usage.
	"""

	class Action(models.TextChoices):
		QUOTATION_STATUS_CHANGED = "quotation_status_changed", "Quotation status changed"
		DOCUMENT_UPLOADED = "document_uploaded", "Document uploaded"
		BID_CREATED = "bid_created", "Bid created"
		BID_UPDATED = "bid_updated", "Bid updated"

	action = models.CharField(max_length=50, choices=Action.choices)
	actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	client = models.ForeignKey("clients.Client", on_delete=models.SET_NULL, null=True, blank=True)
	entity_type = models.CharField(max_length=50)
	entity_id = models.PositiveIntegerField(null=True, blank=True)
	summary = models.CharField(max_length=255, blank=True)
	meta = models.JSONField(blank=True, default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"{self.action} ({self.entity_type}:{self.entity_id})"
