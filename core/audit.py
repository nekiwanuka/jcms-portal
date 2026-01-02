from __future__ import annotations

from typing import Any

from django.db import transaction

from core.models import AuditEvent


def log_event(
	*,
	action: str,
	actor,
	entity=None,
	client=None,
	summary: str = "",
	meta: dict[str, Any] | None = None,
) -> None:
	"""Create an AuditEvent safely (never raises to caller).

	`entity_type` is a simple string (not ContentType-based) to keep this lightweight.
	"""
	try:
		entity_type = ""
		entity_id = None
		if entity is not None:
			entity_type = entity.__class__.__name__.lower()
			entity_id = getattr(entity, "pk", None)

		payload = meta or {}
		with transaction.atomic():
			AuditEvent.objects.create(
				action=action,
				actor=actor if getattr(actor, "is_authenticated", False) else None,
				client=client,
				entity_type=entity_type,
				entity_id=entity_id,
				summary=summary[:255],
				meta=payload,
			)
	except Exception:
		# Audit should never block primary workflow.
		return
