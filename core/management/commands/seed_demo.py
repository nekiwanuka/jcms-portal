from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
	help = "Create fresh demo data for local testing."

	def add_arguments(self, parser):
		parser.add_argument("--clients", type=int, default=5)
		parser.add_argument("--quotations-per-client", type=int, default=2)
		parser.add_argument("--invoices-per-client", type=int, default=2)
		parser.add_argument("--payments-per-invoice", type=int, default=0)
		parser.add_argument("--appointments-per-client", type=int, default=1)
		parser.add_argument("--documents-per-invoice", type=int, default=1)
		parser.add_argument("--documents-per-payment", type=int, default=0)
		parser.add_argument("--admin-email", type=str, default="admin@jambas.local")
		parser.add_argument("--admin-password", type=str, default="Admin12345!")

	def handle(self, *args, **options):
		from core.models import Branch
		from clients.models import Client
		from inventory.models import Product, ProductCategory
		from invoices.models import Invoice, InvoiceItem, Payment
		from sales.models import Quotation, QuotationItem
		from services.models import Service, ServiceCategory
		from appointments.models import Appointment
		from documents.models import Document

		admin_email: str = str(options.get("admin_email") or "admin@jambas.local").strip().lower()
		admin_password: str = str(options.get("admin_password") or "Admin12345!")

		clients_count = max(1, int(options.get("clients") or 5))
		quotations_per_client = max(0, int(options.get("quotations_per_client") or 2))
		invoices_per_client = max(0, int(options.get("invoices_per_client") or 2))
		payments_per_invoice = max(0, int(options.get("payments_per_invoice") or 0))
		appointments_per_client = max(0, int(options.get("appointments_per_client") or 1))
		documents_per_invoice = max(0, int(options.get("documents_per_invoice") or 1))
		documents_per_payment = max(0, int(options.get("documents_per_payment") or 0))

		User = get_user_model()
		admin_user, created = User.objects.get_or_create(
			email=admin_email,
			defaults={
				"is_staff": True,
				"is_superuser": True,
				"is_active": True,
				"role": getattr(User, "Role", None).ADMIN if hasattr(User, "Role") else "admin",
			},
		)
		if created:
			admin_user.set_password(admin_password)
			admin_user.save(update_fields=["password"])
			self.stdout.write(self.style.SUCCESS(f"Created admin user: {admin_email}"))
		else:
			admin_user.set_password(admin_password)
			admin_user.is_staff = True
			admin_user.is_superuser = True
			admin_user.is_active = True
			try:
				admin_user.role = getattr(User, "Role", None).ADMIN
			except Exception:
				pass
			admin_user.save()
			self.stdout.write(self.style.WARNING(f"Updated existing admin user password: {admin_email}"))

		branch, _ = Branch.objects.get_or_create(
			code="MAIN",
			defaults={
				"name": "Main Branch",
				"address": "Kampala, Uganda",
				"phone": "+256 200 902 849",
				"is_active": True,
			},
		)

		clients: list[Client] = []
		primary_client, _ = Client.objects.get_or_create(
			client_type=Client.ClientType.COMPANY,
			company_name="ABC Medical Ltd",
			defaults={
				"branch": branch,
				"contact_person": "Jane Doe",
				"phone": "+256 700 000 000",
				"email": "procurement@abcmedical.test",
				"physical_address": "Plot 1, Kampala",
				"status": Client.Status.ACTIVE,
			},
		)
		clients.append(primary_client)

		seed_specs = [
			(
				Client.ClientType.COMPANY,
				{"company_name": "Kampala Stationers Co."},
				{
					"branch": branch,
					"contact_person": "Peter Okello",
					"phone": "+256 701 111 111",
					"email": "orders@kampalastationers.test",
					"physical_address": "Nasser Road, Kampala",
					"status": Client.Status.ACTIVE,
				},
			),
			(
				Client.ClientType.COMPANY,
				{"company_name": "Sunrise Supplies Ltd"},
				{
					"branch": branch,
					"contact_person": "Sarah Namulindwa",
					"phone": "+256 702 222 222",
					"email": "procurement@sunrisesupplies.test",
					"physical_address": "Nakawa, Kampala",
					"status": Client.Status.ACTIVE,
				},
			),
			(
				Client.ClientType.INDIVIDUAL,
				{"full_name": "Paul Kato"},
				{
					"branch": branch,
					"phone": "+256 703 333 333",
					"email": "paul.kato@test.example",
					"physical_address": "Kireka, Wakiso",
					"status": Client.Status.ACTIVE,
				},
			),
			(
				Client.ClientType.INDIVIDUAL,
				{"full_name": "Grace Achieng"},
				{
					"branch": branch,
					"phone": "+256 704 444 444",
					"email": "grace.achieng@test.example",
					"physical_address": "Ntinda, Kampala",
					"status": Client.Status.ACTIVE,
				},
			),
		]

		for client_type, lookup, defaults in seed_specs[: max(0, clients_count - 1)]:
			client_obj, _ = Client.objects.get_or_create(client_type=client_type, defaults=defaults, **lookup)
			clients.append(client_obj)

		if len(clients) < clients_count:
			start = len(clients) + 1
			for i in range(start, clients_count + 1):
				if i % 2 == 0:
					client_obj, _ = Client.objects.get_or_create(
						client_type=Client.ClientType.COMPANY,
						company_name=f"Demo Company {i:02d} Ltd",
						defaults={
							"branch": branch,
							"contact_person": f"Contact {i:02d}",
							"phone": f"+256 70{i % 10} {i:03d} {i:03d}",
							"email": f"procurement{i:02d}@democompany.test",
							"physical_address": "Kampala, Uganda",
							"status": Client.Status.ACTIVE,
						},
					)
				else:
					client_obj, _ = Client.objects.get_or_create(
						client_type=Client.ClientType.INDIVIDUAL,
						full_name=f"Demo Person {i:02d}",
						defaults={
							"branch": branch,
							"phone": f"+256 70{i % 10} {i:03d} {i:03d}",
							"email": f"person{i:02d}@test.example",
							"physical_address": "Kampala, Uganda",
							"status": Client.Status.ACTIVE,
						},
					)
				clients.append(client_obj)

		category, _ = ProductCategory.objects.get_or_create(
			name="GENERAL",
			defaults={"category_type": ProductCategory.CategoryType.GENERAL},
		)
		product, _ = Product.objects.get_or_create(
			name="A4 Printing Paper",
			category=category,
			defaults={
				"branch": branch,
				"unit": "ream",
				"description": "A4 printing paper (ream)",
				"unit_price": Decimal("55000.00"),
				"cost_price": Decimal("48000.00"),
				"stock_quantity": Decimal("500.00"),
				"low_stock_threshold": Decimal("20.00"),
				"vat_exempt": False,
				"is_active": True,
			},
		)

		service_category, _ = ServiceCategory.objects.get_or_create(name="DESIGN")
		service, _ = Service.objects.get_or_create(
			branch=branch,
			category=service_category,
			name="Design",
			defaults={
				"description": "Design & layout for print jobs",
				"unit_price": Decimal("150000.00"),
				"service_charge": Decimal("70000.00"),
				"is_active": True,
			},
		)

		def _make_document(*, client: Client, doc_type: str, title: str, related_invoice=None, related_payment=None, related_quotation=None):
			payload = f"Seeded document: {title}".encode("utf-8")
			content = ContentFile(payload, name=f"{title.replace(' ', '_')}.txt")
			doc = Document.objects.create(
				branch=branch,
				client=client,
				related_invoice=related_invoice,
				related_payment=related_payment,
				related_quotation=related_quotation,
				uploaded_by=admin_user,
				doc_type=doc_type,
				title=title,
				file=content,
				approval_workflow=Document.ApprovalWorkflow.SINGLE,
				requires_signature=True,
			)

			variant = abs(hash(title)) % 4
			if variant == 1:
				doc.verification_status = Document.VerificationStatus.UNDER_REVIEW
				doc.save(update_fields=["verification_status"])
			elif variant == 2:
				doc.verification_status = Document.VerificationStatus.APPROVED
				doc.approved_at = timezone.now()
				doc.save(update_fields=["verification_status", "approved_at"])
				try:
					doc.approved_by.add(admin_user)
				except Exception:
					pass
			elif variant == 3:
				doc.verification_status = Document.VerificationStatus.REJECTED
				doc.rejected_by = admin_user
				doc.rejected_at = timezone.now()
				doc.save(update_fields=["verification_status", "rejected_by", "rejected_at"])

			if abs(hash(title)) % 5 == 0:
				doc.expiry_date = timezone.localdate() + timezone.timedelta(days=10)
				doc.save(update_fields=["expiry_date"])

			return doc

		quote_status_cycle = [Quotation.Status.DRAFT, Quotation.Status.SENT, Quotation.Status.ACCEPTED, Quotation.Status.REJECTED]
		invoice_status_cycle = [Invoice.Status.DRAFT, Invoice.Status.ISSUED]

		quotes_created = 0
		invoices_created = 0
		payments_created = 0
		appointments_created = 0
		documents_created = 0

		for idx, client in enumerate(clients, start=1):
			for a_idx in range(appointments_per_client):
				scheduled_for = timezone.now() + timezone.timedelta(days=((idx + a_idx) % 10) - 3, hours=(a_idx % 5) + 9)
				Appointment.objects.create(
					branch=branch,
					client=client,
					assigned_to=admin_user,
					created_by=admin_user,
					appointment_type=(Appointment.AppointmentType.CONSULTATION if (a_idx % 2 == 0) else Appointment.AppointmentType.PRINTING_JOB),
					status=(Appointment.Status.CONFIRMED if (a_idx % 3 == 0) else Appointment.Status.PENDING),
					scheduled_for=scheduled_for,
					meeting_mode=Appointment.MeetingMode.PHYSICAL,
					meeting_location="Main Branch",
					notes="Seeded appointment for testing.",
				)
				appointments_created += 1

			for q_idx in range(quotations_per_client):
				valid_until = timezone.localdate() + timezone.timedelta(days=7 + ((idx + q_idx) % 21))
				quote = Quotation.objects.create(
					branch=branch,
					client=client,
					created_by=admin_user,
					status=quote_status_cycle[(idx + q_idx) % len(quote_status_cycle)],
					category=Quotation.Category.PRINTING,
					vat_enabled=True,
					discount_amount=Decimal("0.00"),
					valid_until=valid_until,
					notes="",
				)
				QuotationItem.objects.create(
					quotation=quote,
					product=product,
					item_name="A4 Paper",
					description="A4 printing paper (ream)",
					quantity=Decimal(str(1 + ((idx + q_idx) % 5))),
					unit_price=Decimal("55000.00"),
					vat_exempt=False,
				)
				QuotationItem.objects.create(
					quotation=quote,
					service=service,
					item_name="Design",
					description="Design & layout for print job",
					quantity=Decimal("1.00"),
					unit_price=Decimal("150000.00"),
					vat_exempt=False,
				)
				try:
					quote.recalculate_amounts(save=True)
				except Exception:
					pass
				quotes_created += 1

			for inv_idx in range(invoices_per_client):
				issued = timezone.localdate() - timezone.timedelta(days=((idx + inv_idx) % 20))
				due = issued + timezone.timedelta(days=14)
				invoice = Invoice.objects.create(
					branch=branch,
					client=client,
					created_by=admin_user,
					status=invoice_status_cycle[(idx + inv_idx) % len(invoice_status_cycle)],
					issued_at=issued,
					due_at=due,
					prepared_by_name="Admin",
					notes="Seeded invoice for testing lists/search/PDF.",
				)
				InvoiceItem.objects.create(
					invoice=invoice,
					product=product,
					description="A4 printing paper (ream)",
					quantity=Decimal(str(1 + ((idx + inv_idx) % 4))),
					unit_cost=Decimal("48000.00"),
					unit_price=Decimal("55000.00"),
					vat_exempt=False,
				)
				InvoiceItem.objects.create(
					invoice=invoice,
					service=service,
					description="Design & layout for print job",
					quantity=Decimal("1.00"),
					unit_cost=Decimal("70000.00"),
					unit_price=Decimal("150000.00"),
					vat_exempt=False,
				)
				invoices_created += 1

				for d_idx in range(documents_per_invoice):
					_make_document(
						client=client,
						doc_type=Document.DocumentType.INVOICE,
						title=f"Invoice Doc {invoice.number} v{d_idx + 1}",
						related_invoice=invoice,
					)
					documents_created += 1

				if inv_idx % 2 == 0:
					for p_idx in range(payments_per_invoice):
						payment = Payment.objects.create(
							invoice=invoice,
							method=Payment.Method.CASH,
							amount=invoice.total(),
							reference=f"CASH-{invoice.number}-{p_idx + 1}",
							paid_at=timezone.now() - timezone.timedelta(days=((idx + inv_idx) % 10)),
							recorded_by=admin_user,
							notes="Seeded payment.",
						)
						payments_created += 1

						for d_idx in range(documents_per_payment):
							_make_document(
								client=client,
								doc_type=Document.DocumentType.RECEIPT,
								title=f"Receipt Doc {payment.receipt_number} v{d_idx + 1}",
								related_payment=payment,
							)
							documents_created += 1

		self.stdout.write(self.style.SUCCESS("Demo data created."))
		self.stdout.write(f"Admin login: {admin_email} / {admin_password}")
		self.stdout.write(f"Clients: {len(clients)}")
		self.stdout.write(f"Quotations: {quotes_created}")
		self.stdout.write(f"Invoices: {invoices_created}")
		self.stdout.write(f"Payments/Receipts: {payments_created}")
		self.stdout.write(f"Appointments: {appointments_created}")
		self.stdout.write(f"Documents: {documents_created}")
		self.stdout.write("Quick test URLs after starting the server:")
		first_quote = Quotation.objects.order_by("id").first()
		first_invoice = Invoice.objects.order_by("id").first()
		if first_quote:
			self.stdout.write(f"- /quotations/{first_quote.pk}/pdf/?inline=1")
			self.stdout.write(f"- /quotations/{first_quote.pk}/proforma/pdf/?inline=1")
		if first_invoice:
			self.stdout.write(f"- /invoices/{first_invoice.pk}/pdf/?inline=1")
