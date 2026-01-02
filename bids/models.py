from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.utils import timezone


class BidSequence(models.Model):
	year = models.PositiveIntegerField(unique=True)
	last_number = models.PositiveIntegerField(default=0)


class Bid(models.Model):
	class Status(models.TextChoices):
		DRAFT = "draft", "Draft"
		SUBMITTED = "submitted", "Submitted"
		UNDER_REVIEW = "under_review", "Under Review"
		WON = "won", "Won"
		LOST = "lost", "Lost"
		CANCELLED = "cancelled", "Cancelled"

	class SubmissionMethod(models.TextChoices):
		EMAIL = "email", "Email"
		PORTAL = "portal", "Portal"
		PHYSICAL = "physical", "Physical"
		OTHER = "other", "Other"

	class Category(models.TextChoices):
		PRINTING = "printing", "Printing"
		BRANDING = "branding", "Branding"
		IT = "it", "IT"
		MEDICAL = "medical", "Medical"
		PPE = "ppe", "PPE"
		OTHER = "other", "Other"

	quotation = models.ForeignKey(
		"sales.Quotation",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="bids",
	)
	client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="bids")
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	submitted_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="submitted_bids",
	)

	bid_number = models.CharField(max_length=30, unique=True, blank=True)
	title = models.CharField(max_length=255)
	reference_number = models.CharField(max_length=120, blank=True)
	tender_reference = models.CharField(max_length=120, blank=True)
	submission_method = models.CharField(max_length=20, choices=SubmissionMethod.choices, default=SubmissionMethod.EMAIL)
	submission_method_other = models.CharField(max_length=120, blank=True, default="", verbose_name="Other (specify)")
	category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
	category_other = models.CharField(max_length=120, blank=True, default="", verbose_name="Other (specify)")
	amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
	closing_date = models.DateField()
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
	# Legacy field kept for backward compatibility; UI should use `status`.
	outcome = models.CharField(max_length=20, default="pending")

	document = models.FileField(
		upload_to="bids/",
		blank=True,
		null=True,
		validators=[FileExtensionValidator(["pdf"])],
	)
	required_documents = models.FileField(
		upload_to="bids/required/",
		blank=True,
		null=True,
		validators=[FileExtensionValidator(["pdf"])],
	)
	compliance_notes = models.TextField(blank=True)
	notes = models.TextField(blank=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self) -> str:
		return self.bid_number or f"Bid #{self.pk}"

	def _next_number(self) -> str:
		year = timezone.localdate().year
		with transaction.atomic():
			seq, _ = BidSequence.objects.select_for_update().get_or_create(year=year)
			seq.last_number += 1
			seq.save(update_fields=["last_number"])
			return f"BID-{year}-{seq.last_number:05d}"

	def save(self, *args, **kwargs):
		if not self.bid_number:
			self.bid_number = self._next_number()
		super().save(*args, **kwargs)

	@property
	def is_locked(self) -> bool:
		return self.status in {
			self.Status.SUBMITTED,
			self.Status.UNDER_REVIEW,
			self.Status.WON,
			self.Status.LOST,
			self.Status.CANCELLED,
		}

	@property
	def submission_method_label(self) -> str:
		if self.submission_method == self.SubmissionMethod.OTHER and (self.submission_method_other or "").strip():
			return self.submission_method_other.strip()
		return self.get_submission_method_display()

	@property
	def category_label(self) -> str:
		if self.category == self.Category.OTHER and (self.category_other or "").strip():
			return self.category_other.strip()
		return self.get_category_display()

	@property
	def badge_class(self) -> str:
		return {
			self.Status.DRAFT: "text-bg-warning",
			self.Status.SUBMITTED: "text-bg-primary",
			self.Status.UNDER_REVIEW: "text-bg-info",
			self.Status.WON: "text-bg-success",
			self.Status.LOST: "text-bg-danger",
			self.Status.CANCELLED: "text-bg-secondary",
		}.get(self.status, "text-bg-secondary")
