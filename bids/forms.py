from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import Bid


class BidForm(forms.ModelForm):	
	class Meta:
		model = Bid
		exclude = ["bid_number", "created_by", "submitted_by", "created_at", "updated_at", "status", "outcome"]
		widgets = {
			"closing_date": forms.DateInput(attrs={"type": "date"}),
			"notes": forms.Textarea(attrs={"rows": 3}),
			"compliance_notes": forms.Textarea(attrs={"rows": 3}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")

	def clean_amount(self):
		amount = self.cleaned_data.get("amount")
		if amount is None:
			return amount
		if amount < Decimal("0.00"):
			raise forms.ValidationError("Bid amount cannot be negative.")
		return amount

	def clean_closing_date(self):
		deadline = self.cleaned_data.get("closing_date")
		if not deadline:
			return deadline
		if deadline < timezone.localdate():
			raise forms.ValidationError("Closing date cannot be in the past.")
		return deadline

	def clean_document(self):
		doc = self.cleaned_data.get("document")
		if not doc:
			return doc
		# Basic hardening: size + content type check (still rely on extension validator too)
		max_bytes = 15 * 1024 * 1024
		if getattr(doc, "size", 0) and doc.size > max_bytes:
			raise forms.ValidationError("Document too large (max 15MB).")
		content_type = getattr(doc, "content_type", "") or ""
		if content_type and content_type not in {"application/pdf", "application/x-pdf"}:
			raise forms.ValidationError("Only PDF documents are allowed.")
		return doc

	def clean_required_documents(self):
		doc = self.cleaned_data.get("required_documents")
		if not doc:
			return doc
		max_bytes = 15 * 1024 * 1024
		if getattr(doc, "size", 0) and doc.size > max_bytes:
			raise forms.ValidationError("Document too large (max 15MB).")
		content_type = getattr(doc, "content_type", "") or ""
		if content_type and content_type not in {"application/pdf", "application/x-pdf"}:
			raise forms.ValidationError("Only PDF documents are allowed.")
		return doc

	def clean(self):
		cleaned = super().clean()

		submission_method = cleaned.get("submission_method")
		submission_other = (cleaned.get("submission_method_other") or "").strip()
		if submission_method == Bid.SubmissionMethod.OTHER:
			if not submission_other:
				self.add_error("submission_method_other", "Please specify the submission method.")
		else:
			cleaned["submission_method_other"] = ""

		category = cleaned.get("category")
		category_other = (cleaned.get("category_other") or "").strip()
		if category == Bid.Category.OTHER:
			if not category_other:
				self.add_error("category_other", "Please specify the 'Other' category.")
		else:
			cleaned["category_other"] = ""

		quotation = cleaned.get("quotation")
		client = cleaned.get("client")
		if quotation and client and quotation.client_id != client.id:
			self.add_error("quotation", "Selected quotation does not match the chosen client.")
		if self.instance and self.instance.pk and self.instance.is_locked:
			raise forms.ValidationError("Submitted bids are read-only and cannot be edited.")
		return cleaned
