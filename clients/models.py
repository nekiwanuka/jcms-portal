from django.db import models


class Client(models.Model):
	class ClientType(models.TextChoices):
		INDIVIDUAL = "individual", "Individual"
		COMPANY = "company", "Company"

	class Status(models.TextChoices):
		PROSPECT = "prospect", "Prospect"
		ACTIVE = "active", "Active"

	branch = models.ForeignKey(
		"core.Branch",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="clients",
	)

	client_type = models.CharField(max_length=20, choices=ClientType.choices)
	full_name = models.CharField(max_length=255, blank=True)
	company_name = models.CharField(max_length=255, blank=True)

	contact_person = models.CharField(max_length=255, blank=True)
	phone = models.CharField(max_length=50, blank=True)
	email = models.EmailField(blank=True)
	physical_address = models.CharField(max_length=255, blank=True)

	tin = models.CharField(max_length=50, blank=True)
	nin = models.CharField(max_length=50, blank=True)

	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROSPECT)

	notes = models.TextField(blank=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		name = self.company_name if self.client_type == self.ClientType.COMPANY else self.full_name
		return name or f"Client #{self.pk}"
