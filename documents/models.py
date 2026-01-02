import os
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def document_upload_to(instance, filename: str) -> str:
	ext = os.path.splitext(filename)[1].lower()
	client_id = instance.client_id or "unknown"
	return f"clients/{client_id}/documents/{instance.doc_type}/{uuid.uuid4().hex}{ext}"


class Document(models.Model):
	class DocumentType(models.TextChoices):
		INVOICE = "invoice", "Invoice"
		QUOTATION = "quotation", "Quotation"
		PROFORMA = "proforma", "Proforma"
		RECEIPT = "receipt", "Receipt"
		TENDER = "tender", "Tender Document"
		COMPLIANCE = "compliance", "Compliance File"
		CONTRACT = "contract", "Contract"
		ID = "id", "ID"
		OTHER = "other", "Other"

	branch = models.ForeignKey(
		"core.Branch",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="documents",
	)
	client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="documents")
	related_quotation = models.ForeignKey(
		"sales.Quotation",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="documents",
	)
	related_invoice = models.ForeignKey(
		"invoices.Invoice",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="documents",
	)
	related_payment = models.ForeignKey(
		"invoices.Payment",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="documents",
	)
	related_bid = models.ForeignKey(
		"bids.Bid",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="documents",
	)
	uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

	doc_type = models.CharField(max_length=20, choices=DocumentType.choices)
	doc_type_other = models.CharField(max_length=120, blank=True, default="", verbose_name="Other (specify)")
	title = models.CharField(max_length=255, blank=True)
	version = models.PositiveIntegerField(default=1)
	file = models.FileField(upload_to=document_upload_to)
	notes = models.TextField(blank=True)
	uploaded_at = models.DateTimeField(default=timezone.now)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return self.title or f"{self.doc_type_label} ({self.client})"

	@property
	def doc_type_label(self) -> str:
		if self.doc_type == self.DocumentType.OTHER and (self.doc_type_other or "").strip():
			return self.doc_type_other.strip()
		return self.get_doc_type_display()

	def save(self, *args, **kwargs):
		if not self.pk:
			# Basic versioning by (client, doc_type, title, related objects)
			base_qs = Document.objects.filter(
				client_id=self.client_id,
				doc_type=self.doc_type,
				title=self.title,
				related_invoice_id=self.related_invoice_id,
				related_payment_id=self.related_payment_id,
				related_quotation_id=self.related_quotation_id,
				related_bid_id=self.related_bid_id,
			)
			latest = base_qs.order_by("-version").values_list("version", flat=True).first()
			if latest:
				self.version = int(latest) + 1
		super().save(*args, **kwargs)
