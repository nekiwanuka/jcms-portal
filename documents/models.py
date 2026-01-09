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

	class VerificationStatus(models.TextChoices):
		PENDING = "pending", "Pending Verification"
		UNDER_REVIEW = "under_review", "Under Review"
		APPROVED = "approved", "Approved"
		REJECTED = "rejected", "Rejected"
		EXPIRED = "expired", "Expired"

	class ApprovalWorkflow(models.TextChoices):
		NONE = "none", "No Approval Required"
		SINGLE = "single", "Single Approver"
		MULTI = "multi", "Multiple Approvers"
		SEQUENTIAL = "sequential", "Sequential Approval"

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

	# Document verification fields
	verification_status = models.CharField(
		max_length=20,
		choices=VerificationStatus.choices,
		default=VerificationStatus.PENDING,
		verbose_name="Verification Status"
	)
	approval_workflow = models.CharField(
		max_length=20,
		choices=ApprovalWorkflow.choices,
		default=ApprovalWorkflow.NONE,
		verbose_name="Approval Workflow"
	)
	requires_signature = models.BooleanField(default=False, verbose_name="Requires Digital Signature")
	is_signed = models.BooleanField(default=False, verbose_name="Digitally Signed")
	signature_data = models.JSONField(null=True, blank=True, verbose_name="Signature Data")
	expiry_date = models.DateField(null=True, blank=True, verbose_name="Expiry Date")
	is_template = models.BooleanField(default=False, verbose_name="Is Template")
	template_fields = models.JSONField(null=True, blank=True, verbose_name="Template Fields")

	# Approval workflow fields
	approved_by = models.ManyToManyField(
		settings.AUTH_USER_MODEL,
		related_name="approved_documents",
		blank=True,
		verbose_name="Approved By"
	)
	rejected_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="rejected_documents",
		verbose_name="Rejected By"
	)
	approval_notes = models.TextField(blank=True, verbose_name="Approval Notes")
	approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Approved At")
	rejected_at = models.DateTimeField(null=True, blank=True, verbose_name="Rejected At")

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
		# Ensure every document has a human-friendly title.
		# - Upload form enforces this, but keep a model-level fallback for
		#   programmatic creations and legacy paths.
		if not (self.title or "").strip():
			base = ""
			try:
				name = getattr(self.file, "name", "") or ""
				base = os.path.splitext(os.path.basename(name))[0].strip()
			except Exception:
				base = ""
			self.title = base or f"{self.doc_type_label}"

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

			# Set initial verification status based on workflow
			if self.approval_workflow != self.ApprovalWorkflow.NONE:
				self.verification_status = self.VerificationStatus.PENDING
			else:
				self.verification_status = self.VerificationStatus.APPROVED

		super().save(*args, **kwargs)

	@property
	def is_expired(self):
		"""Check if document has expired."""
		if self.expiry_date:
			return timezone.now().date() > self.expiry_date
		return False

	@property
	def days_until_expiry(self):
		"""Calculate days until expiry."""
		if self.expiry_date:
			delta = self.expiry_date - timezone.now().date()
			return delta.days
		return None

	def approve(self, user, notes=""):
		"""Approve the document."""
		from django.utils import timezone

		if self.approval_workflow == self.ApprovalWorkflow.NONE:
			return True

		self.approved_by.add(user)
		self.approval_notes = notes
		self.approved_at = timezone.now()

		# Check if approval is complete based on workflow
		if self._is_approval_complete():
			self.verification_status = self.VerificationStatus.APPROVED

		self.save()
		return True

	def reject(self, user, notes=""):
		"""Reject the document."""
		from django.utils import timezone

		self.rejected_by = user
		self.approval_notes = notes
		self.rejected_at = timezone.now()
		self.verification_status = self.VerificationStatus.REJECTED
		self.save()
		return True

	def _is_approval_complete(self):
		"""Check if approval workflow is complete."""
		if self.approval_workflow == self.ApprovalWorkflow.SINGLE:
			return self.approved_by.exists()
		elif self.approval_workflow == self.ApprovalWorkflow.MULTI:
			# For multi-approval, we could implement logic for required number of approvers
			# For now, assume any approval completes it
			return self.approved_by.exists()
		elif self.approval_workflow == self.ApprovalWorkflow.SEQUENTIAL:
			# For sequential, we could implement role-based approval chains
			# For now, assume single approval completes it
			return self.approved_by.exists()
		return False

	def add_digital_signature(self, signature_data):
		"""Add digital signature to document."""
		self.signature_data = signature_data
		self.is_signed = True
		self.save()

	def remove_digital_signature(self):
		"""Remove digital signature from document."""
		self.signature_data = None
		self.is_signed = False
		self.save()

	def create_from_template(self, field_values):
		"""Create a new document from this template."""
		if not self.is_template:
			return None

		# This would implement template processing logic
		# For now, return None as placeholder
		return None
