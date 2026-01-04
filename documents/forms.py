from django import forms

from .models import Document


class DocumentForm(forms.ModelForm):
	class Meta:
		model = Document
		exclude = ["uploaded_by", "uploaded_at", "created_at", "related_invoice", "related_payment"]
		widgets = {
			"notes": forms.Textarea(attrs={"rows": 3}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if "title" in self.fields:
			self.fields["title"].required = True
			self.fields["title"].label = "Document Name"
			self.fields["title"].help_text = "Use a clear name (e.g., 'NDA - ACME Ltd', 'Tax Clearance', 'Company Profile')."
			self.fields["title"].widget.attrs.setdefault("placeholder", "Enter a descriptive document name")
			self.fields["title"].widget.attrs.setdefault("autocomplete", "off")

		for field in self.fields.values():
			widget = field.widget
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")

		# Make file required on create
		if self.instance and self.instance.pk:
			self.fields["file"].required = False

	def clean(self):
		cleaned = super().clean()
		title = (cleaned.get("title") or "").strip()
		uploaded = cleaned.get("file")
		if not title and uploaded is not None:
			# Fall back to the uploaded filename (without extension).
			name = getattr(uploaded, "name", "") or ""
			if name:
				title = name.rsplit("/", 1)[-1]
				title = title.rsplit("\\", 1)[-1]
				title = title.rsplit(".", 1)[0].strip()
				cleaned["title"] = title

		# Disallow numeric-only titles ("numbers alone are not enough").
		if title and not any(ch.isalpha() for ch in title):
			self.add_error("title", "Please enter a descriptive name (include at least one letter).")

		doc_type = cleaned.get("doc_type")
		doc_type_other = (cleaned.get("doc_type_other") or "").strip()
		if doc_type == Document.DocumentType.OTHER:
			if not doc_type_other:
				self.add_error("doc_type_other", "Please specify the 'Other' document type.")
		else:
			cleaned["doc_type_other"] = ""
		return cleaned
