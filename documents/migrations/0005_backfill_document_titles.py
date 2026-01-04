from __future__ import annotations

import os

from django.db import migrations


def backfill_document_titles(apps, schema_editor):
	Document = apps.get_model("documents", "Document")

	qs = Document.objects.filter(title="")
	for doc in qs.iterator():
		base = ""
		try:
			name = getattr(doc.file, "name", "") or ""
			base = os.path.splitext(os.path.basename(name))[0].strip()
		except Exception:
			base = ""
		# Ensure the backfilled title includes letters.
		title = base or f"{doc.get_doc_type_display()} {doc.pk}"
		Document.objects.filter(pk=doc.pk, title="").update(title=title)


class Migration(migrations.Migration):
	dependencies = [
		("documents", "0004_document_related_invoice_related_payment"),
	]

	operations = [
		migrations.RunPython(backfill_document_titles, reverse_code=migrations.RunPython.noop),
	]
