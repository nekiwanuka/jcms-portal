from django import forms
from django.contrib.auth import password_validation

from .models import User


class AdminUserCreationForm(forms.ModelForm):
	password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput)
	password2 = forms.CharField(label="Password confirmation", strip=False, widget=forms.PasswordInput)

	class Meta:
		model = User
		fields = ("email", "full_name", "phone", "role", "is_active", "is_staff", "is_superuser")

	def clean_email(self):
		email = (self.cleaned_data.get("email") or "").strip().lower()
		if not email:
			raise forms.ValidationError("Email is required.")
		if User.objects.filter(email=email).exists():
			raise forms.ValidationError("A user with that email already exists.")
		return email

	def clean(self):
		cleaned = super().clean()
		password1 = cleaned.get("password1")
		password2 = cleaned.get("password2")
		if password1 and password2 and password1 != password2:
			raise forms.ValidationError("Passwords do not match.")
		if password1:
			password_validation.validate_password(password1, self.instance)
		return cleaned

	def save(self, commit=True):
		user: User = super().save(commit=False)
		user.email = (user.email or "").strip().lower()
		user.set_password(self.cleaned_data["password1"])
		if commit:
			user.save()
			self.save_m2m()
		return user


class AdminUserChangeForm(forms.ModelForm):
	"""Admin change form for our email-based user."""

	class Meta:
		model = User
		fields = (
			"email",
			"full_name",
			"phone",
			"role",
			"is_active",
			"is_staff",
			"is_superuser",
			"groups",
			"user_permissions",
		)

	def clean_email(self):
		email = (self.cleaned_data.get("email") or "").strip().lower()
		if not email:
			raise forms.ValidationError("Email is required.")
		qs = User.objects.filter(email=email)
		if self.instance.pk:
			qs = qs.exclude(pk=self.instance.pk)
		if qs.exists():
			raise forms.ValidationError("A user with that email already exists.")
		return email
