from django import forms

from .models import Client


class ClientForm(forms.ModelForm):
	"""Client create/edit form.

	Uses Bootstrap-friendly widgets.
	"""

	class Meta:
		model = Client
		fields = "__all__"
		widgets = {
			"notes": forms.Textarea(attrs={"rows": 3}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		for field in self.fields.values():
			widget = field.widget
			# Bootstrap 5 styling
			if widget.__class__.__name__ in {"CheckboxInput"}:
				widget.attrs.setdefault("class", "form-check-input")
			elif widget.__class__.__name__ in {"Select", "SelectMultiple"}:
				widget.attrs.setdefault("class", "form-select")
			else:
				widget.attrs.setdefault("class", "form-control")

	def clean(self):
		"""Lightweight business validation.

		- Individual clients should have `full_name`.
		- Company clients should have `company_name`.
		- At least one contact (phone or email) is recommended.
		"""
		cleaned = super().clean()
		client_type = cleaned.get("client_type")
		full_name = (cleaned.get("full_name") or "").strip()
		company_name = (cleaned.get("company_name") or "").strip()
		phone = (cleaned.get("phone") or "").strip()
		email = (cleaned.get("email") or "").strip()

		if client_type == Client.ClientType.INDIVIDUAL and not full_name:
			self.add_error("full_name", "Full name is required for Individual clients.")
		if client_type == Client.ClientType.COMPANY and not company_name:
			self.add_error("company_name", "Company name is required for Company clients.")
		if not phone and not email:
			self.add_error("phone", "Provide at least a phone number or an email.")
			self.add_error("email", "Provide at least an email or a phone number.")

		return cleaned
