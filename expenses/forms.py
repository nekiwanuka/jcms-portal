from decimal import Decimal

from django import forms

from .models import Expense


class ExpenseForm(forms.ModelForm):
	class Meta:
		model = Expense
		exclude = ["created_by", "created_at"]
		widgets = {
			"expense_date": forms.DateInput(attrs={"type": "date"}),
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
		if amount <= Decimal("0.00"):
			raise forms.ValidationError("Amount must be greater than 0.")
		return amount

	def clean(self):
		cleaned = super().clean()
		category = cleaned.get("category")
		category_other = (cleaned.get("category_other") or "").strip()
		if category == Expense.Category.OTHER:
			if not category_other:
				self.add_error("category_other", "Please specify the 'Other' category.")
		else:
			cleaned["category_other"] = ""
		return cleaned
