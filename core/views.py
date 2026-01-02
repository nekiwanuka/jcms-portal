import csv
from datetime import date as _date
from datetime import datetime as _datetime
from io import BytesIO
from urllib.parse import urlencode
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _role(user) -> str | None:
	return getattr(user, "role", None)


def _is_admin(user) -> bool:
	return bool(user and user.is_authenticated and (getattr(user, "is_superuser", False) or _role(user) == "admin"))


def _can_view_income(user) -> bool:
	return bool(user and user.is_authenticated and (getattr(user, "is_superuser", False) or _role(user) in {"admin", "manager"}))


def _require_admin(request):
	if _is_admin(request.user):
		return None
	messages.error(request, "You do not have permission to access that page.")
	return redirect("dashboard")


def _get_str(request, key: str) -> str:
	return (request.GET.get(key) or "").strip()


def _get_int(request, key: str):
	val = _get_str(request, key)
	if not val:
		return None
	try:
		return int(val)
	except ValueError:
		return None


def _get_bool(request, key: str) -> bool:
	val = _get_str(request, key).lower()
	return val in {"1", "true", "yes", "on"}


def _get_date(request, key: str):
	val = _get_str(request, key)
	if not val:
		return None
	try:
		# Prefer strict date parsing for <input type="date">.
		return _date.fromisoformat(val)
	except ValueError:
		try:
			# Fall back to full ISO (may include time).
			return _datetime.fromisoformat(val).date()
		except ValueError:
			return None


def _get_dt(request, key: str):
	val = _get_str(request, key)
	if not val:
		return None
	try:
		# Accept both "YYYY-MM-DDTHH:MM" (datetime-local) and full ISO forms.
		dt = _datetime.fromisoformat(val)
		return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
	except ValueError:
		return None


def _current_querystring(request) -> str:
	"""Return current GET params as a querystring, prefixed with '?' (or '')."""
	if not request.GET:
		return ""
	return "?" + urlencode({k: v for k, v in request.GET.items() if v not in (None, "")})


def _filter_clients(request, qs):
	q = _get_str(request, "q")
	client_type = _get_str(request, "client_type")
	status = _get_str(request, "status")
	branch_id = _get_int(request, "branch")

	if q:
		from django.db.models import Q
		qs = qs.filter(
			Q(full_name__icontains=q)
			| Q(company_name__icontains=q)
			| Q(contact_person__icontains=q)
			| Q(phone__icontains=q)
			| Q(email__icontains=q)
			| Q(tin__icontains=q)
			| Q(nin__icontains=q)
		)
	if client_type:
		qs = qs.filter(client_type=client_type)
	if status:
		qs = qs.filter(status=status)
	if branch_id is not None:
		qs = qs.filter(branch_id=branch_id)
	return qs


def _filter_invoices(request, qs):
	q = _get_str(request, "q")
	status = _get_str(request, "status")
	branch_id = _get_int(request, "branch")
	issued_from = _get_date(request, "issued_from")
	issued_to = _get_date(request, "issued_to")

	from django.db.models import Q
	if q:
		qs = qs.filter(Q(number__icontains=q) | Q(client__full_name__icontains=q) | Q(client__company_name__icontains=q))
	if status:
		qs = qs.filter(status=status)
	if branch_id is not None:
		qs = qs.filter(branch_id=branch_id)
	if issued_from:
		qs = qs.filter(issued_at__gte=issued_from)
	if issued_to:
		qs = qs.filter(issued_at__lte=issued_to)
	return qs


def _filter_inventory(request, qs):
	q = _get_str(request, "q")
	category_id = _get_int(request, "category")
	supplier_id = _get_int(request, "supplier")
	branch_id = _get_int(request, "branch")
	only_low_stock = _get_bool(request, "low_stock")
	is_active = _get_str(request, "is_active")

	from django.db.models import Q
	if q:
		qs = qs.filter(Q(sku__icontains=q) | Q(name__icontains=q))
	if category_id is not None:
		qs = qs.filter(category_id=category_id)
	if supplier_id is not None:
		qs = qs.filter(supplier_id=supplier_id)
	if branch_id is not None:
		qs = qs.filter(branch_id=branch_id)
	if is_active in {"0", "1"}:
		qs = qs.filter(is_active=(is_active == "1"))
	if only_low_stock:
		qs = qs.filter(stock_quantity__lte=F("low_stock_threshold"))
	return qs


def _filter_appointments(request, qs):
	q = _get_str(request, "q")
	status = _get_str(request, "status")
	appt_type = _get_str(request, "appointment_type")
	branch_id = _get_int(request, "branch")
	from_dt = _get_dt(request, "from")
	to_dt = _get_dt(request, "to")

	from django.db.models import Q
	if q:
		qs = qs.filter(
			Q(client__full_name__icontains=q)
			| Q(client__company_name__icontains=q)
			| Q(assigned_to__email__icontains=q)
			| Q(notes__icontains=q)
		)
	if status:
		qs = qs.filter(status=status)
	if appt_type:
		qs = qs.filter(appointment_type=appt_type)
	if branch_id is not None:
		qs = qs.filter(branch_id=branch_id)
	if from_dt:
		qs = qs.filter(scheduled_for__gte=from_dt)
	if to_dt:
		qs = qs.filter(scheduled_for__lte=to_dt)
	return qs


def _filter_expenses(request, qs):
	q = _get_str(request, "q")
	branch_id = _get_int(request, "branch")
	category = _get_str(request, "category")
	from_date = _get_date(request, "from")
	to_date = _get_date(request, "to")

	from django.db.models import Q
	if q:
		qs = qs.filter(Q(description__icontains=q) | Q(reference__icontains=q))
	if branch_id is not None:
		qs = qs.filter(branch_id=branch_id)
	if category:
		qs = qs.filter(category=category)
	if from_date:
		qs = qs.filter(expense_date__gte=from_date)
	if to_date:
		qs = qs.filter(expense_date__lte=to_date)
	return qs


def _pdf_response(title: str, header: list[str], rows: list[list[str]], filename: str) -> HttpResponse:
	"""Generate a simple, reliable PDF table export.

	Uses ReportLab (already in requirements) for cPanel-friendly PDF creation.
	"""
	buffer = BytesIO()
	doc = SimpleDocTemplate(buffer, pagesize=A4, title=title)
	styles = getSampleStyleSheet()

	elements = [
		Paragraph(title, styles["Title"]),
		Spacer(1, 12),
	]

	data = [header] + rows
	table = Table(data, repeatRows=1)
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
				("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)

	elements.append(table)
	doc.build(elements)

	pdf_bytes = buffer.getvalue()
	buffer.close()

	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	response["Content-Disposition"] = f'attachment; filename="{filename}"'
	return response


@login_required
def dashboard_view(request):
	"""Home dashboard (UI).

	- Login is required (redirects unauthenticated users to LOGIN_URL).
	- Uses Django templates + Bootstrap 5.
	"""
	# Dashboard KPIs (lightweight counts)
	from bids.models import Bid
	from documents.models import Document
	from invoices.models import Invoice
	from invoices.models import Payment
	from sales.models import Quotation

	bids_qs = Bid.objects.all()
	quotes_qs = Quotation.objects.all()
	invoices_qs = Invoice.objects.select_related("client").all()
	documents_qs = Document.objects.select_related("client").all()
	payments_qs = Payment.objects.select_related("invoice", "invoice__client").all()
	context = {
		"bids_counts": {
			"active": bids_qs.filter(status__in={Bid.Status.DRAFT, Bid.Status.SUBMITTED, Bid.Status.UNDER_REVIEW}).count(),
			"won": bids_qs.filter(status=Bid.Status.WON).count(),
			"lost": bids_qs.filter(status=Bid.Status.LOST).count(),
		},
		"quotations_counts": {
			"draft": quotes_qs.filter(status=Quotation.Status.DRAFT).count(),
			"sent": quotes_qs.filter(status=Quotation.Status.SENT).count(),
			"approved": quotes_qs.filter(status=Quotation.Status.ACCEPTED).count(),
			"expired": quotes_qs.filter(status=Quotation.Status.EXPIRED).count(),
			"converted": quotes_qs.filter(status=Quotation.Status.CONVERTED).count(),
		},
		"recent_invoices": invoices_qs.order_by("-created_at")[:5],
		"recent_quotations": quotes_qs.select_related("client").order_by("-created_at")[:5],
		"recent_documents": documents_qs.order_by("-uploaded_at")[:5],
		"recent_payments": payments_qs.order_by("-paid_at", "-id")[:5],
	}
	return render(request, "dashboard/index.html", context)


@login_required
def clients_view(request):
	"""Clients frontend page (UI only).

	This page is intentionally a template-rendered frontend screen (not Django Admin,
	and not DRF). It is safe to expand later with server-side rendered tables/forms.
	"""
	from clients.models import Client

	from core.models import Branch

	clients_qs = Client.objects.select_related("branch").all()
	clients_qs = _filter_clients(request, clients_qs)
	context = {
		"clients": clients_qs[:50],
		"clients_total": clients_qs.count(),
		"clients_active": clients_qs.filter(status=Client.Status.ACTIVE).count(),
		"clients_prospect": clients_qs.filter(status=Client.Status.PROSPECT).count(),
		"branches": Branch.objects.filter(is_active=True),
		"client_type_choices": Client.ClientType.choices,
		"status_choices": Client.Status.choices,
		"filters": {
			"q": _get_str(request, "q"),
			"client_type": _get_str(request, "client_type"),
			"status": _get_str(request, "status"),
			"branch": _get_str(request, "branch"),
		},
		"qs": _current_querystring(request),
	}
	return render(request, "modules/clients.html", context)


@login_required
def add_client(request):
	"""Create a client via a server-rendered ModelForm.

	- Login required
	- CSRF protected (template includes {% csrf_token %})
	- Saves to DB and redirects back to the list page
	"""
	from clients.forms import ClientForm

	if request.method == "POST":
		form = ClientForm(request.POST)
		if form.is_valid():
			form.save()
			return redirect("clients")
	else:
		form = ClientForm()

	return render(request, "modules/add_client.html", {"form": form})


@login_required
def export_clients_csv(request):
	"""Download clients as CSV (server-rendered export, no DRF)."""
	from clients.models import Client

	response = HttpResponse(content_type="text/csv")
	response["Content-Disposition"] = 'attachment; filename="clients.csv"'

	writer = csv.writer(response)
	writer.writerow(["ID", "Type", "Name", "Status", "Phone", "Email", "Created"]) 
	qs = Client.objects.select_related("branch").all().order_by("-created_at")
	qs = _filter_clients(request, qs)
	for c in qs:
		name = c.company_name if c.client_type == Client.ClientType.COMPANY else c.full_name
		writer.writerow([c.pk, c.client_type, name, c.status, c.phone, c.email, c.created_at.date().isoformat()])

	return response


@login_required
def export_clients_pdf(request):
	"""Download clients as PDF (table)."""
	from clients.models import Client

	rows: list[list[str]] = []
	qs = Client.objects.select_related("branch").all().order_by("-created_at")
	qs = _filter_clients(request, qs)
	for c in qs[:200]:
		name = c.company_name if c.client_type == Client.ClientType.COMPANY else c.full_name
		rows.append([
			str(c.pk),
			c.client_type,
			(name or "-")[:40],
			c.status,
			(c.phone or "-")[:18],
			(c.email or "-")[:28],
		])

	return _pdf_response(
		title="Clients",
		header=["ID", "Type", "Name", "Status", "Phone", "Email"],
		rows=rows,
		filename="clients.pdf",
	)


@login_required
def invoices_view(request):
	"""Invoices frontend page (UI only)."""
	from invoices.models import Invoice

	from core.models import Branch

	invoices_qs = Invoice.objects.select_related("client", "branch").all()
	invoices_qs = _filter_invoices(request, invoices_qs)
	context = {
		"invoices": invoices_qs[:50],
		"invoices_total": invoices_qs.count(),
		"invoices_draft": invoices_qs.filter(status=Invoice.Status.DRAFT).count(),
		"invoices_issued": invoices_qs.filter(status=Invoice.Status.ISSUED).count(),
		"invoices_paid": invoices_qs.filter(status=Invoice.Status.PAID).count(),
		"branches": Branch.objects.filter(is_active=True),
		"status_choices": Invoice.Status.choices,
		"filters": {
			"q": _get_str(request, "q"),
			"status": _get_str(request, "status"),
			"branch": _get_str(request, "branch"),
			"issued_from": _get_str(request, "issued_from"),
			"issued_to": _get_str(request, "issued_to"),
		},
		"qs": _current_querystring(request),
	}
	return render(request, "modules/invoices.html", context)


@login_required
def receipts_view(request):
	"""List receipts (payments) with Receipt PDF + Send actions.

	Receipts are per-payment, so this page is effectively a payments/receipts register.
	"""
	from invoices.models import Payment
	from documents.models import Document

	payments = (
		Payment.objects.select_related("invoice", "invoice__client")
		.order_by("-paid_at", "-id")
		.all()[:200]
	)
	payment_ids = [p.id for p in payments]
	docs = Document.objects.filter(related_payment_id__in=payment_ids).order_by("-uploaded_at", "-version")
	archived_by_payment_id = {d.related_payment_id: d for d in docs if d.related_payment_id}
	for p in payments:
		p.archived_receipt_doc = archived_by_payment_id.get(p.id)

	return render(request, "modules/receipts.html", {"payments": payments})


@login_required
def add_invoice(request):
	"""Create an invoice via a server-rendered ModelForm.

	- `created_by` is set from the logged-in user.
	- Invoice number is auto-generated by the model.
	"""
	from invoices.forms import InvoiceForm

	if request.method == "POST":
		form = InvoiceForm(request.POST)
		if form.is_valid():
			invoice = form.save(commit=False)
			invoice.created_by = request.user
			if not (invoice.prepared_by_name or "").strip():
				invoice.prepared_by_name = getattr(request.user, "email", "") or str(request.user)
			invoice.save()

			# If invoice is created from an approved quotation, copy items and mark quotation converted.
			if invoice.quotation_id:
				from invoices.models import InvoiceItem
				from sales.models import Quotation
				quote = invoice.quotation
				if quote and quote.status == Quotation.Status.ACCEPTED:
					if not invoice.items.exists():
						for it in quote.items.all():
							InvoiceItem.objects.create(
								invoice=invoice,
								product=it.product,
								description=(it.item_name or it.description or "Item"),
								quantity=it.quantity,
								unit_price=it.unit_price,
							)
						if (quote.discount_amount or Decimal("0.00")) > Decimal("0.00"):
							InvoiceItem.objects.create(
								invoice=invoice,
								description="Discount",
								quantity=Decimal("1.00"),
								unit_price=(Decimal("0.00") - quote.discount_amount).quantize(Decimal("0.01")),
							)
						invoice.currency = quote.currency
						invoice.vat_rate = quote.vat_rate if quote.vat_enabled else Decimal("0.00")
						invoice.save(update_fields=["currency", "vat_rate"])
					quote.status = Quotation.Status.CONVERTED
					quote.save(update_fields=["status"])
				else:
					messages.warning(request, "Selected quotation must be Approved before conversion.")

			return redirect("invoices")
	else:
		form = InvoiceForm()

	return render(request, "modules/add_invoice.html", {"form": form})


def _quotation_badge_class(status: str) -> str:
	from sales.models import Quotation
	return {
		Quotation.Status.DRAFT: "text-bg-warning",
		Quotation.Status.SENT: "text-bg-primary",
		Quotation.Status.ACCEPTED: "text-bg-success",
		Quotation.Status.REJECTED: "text-bg-danger",
		Quotation.Status.CONVERTED: "text-bg-secondary",
		Quotation.Status.EXPIRED: "text-bg-dark",
	}.get(status, "text-bg-secondary")


@login_required
def quotations_view(request):
	from sales.models import Quotation
	from core.models import Branch
	from django.db.models import Q

	# Auto-expire Draft/Sent quotations after valid_until.
	today = timezone.localdate()
	Quotation.objects.filter(
		status__in=[Quotation.Status.DRAFT, Quotation.Status.SENT],
		valid_until__isnull=False,
		valid_until__lt=today,
	).update(status=Quotation.Status.EXPIRED)

	qs = Quotation.objects.select_related("client", "branch", "created_by").all()
	q = _get_str(request, "q")
	status = _get_str(request, "status")
	category = _get_str(request, "category")
	branch_id = _get_int(request, "branch")

	if q:
		qs = qs.filter(Q(number__icontains=q) | Q(client__full_name__icontains=q) | Q(client__company_name__icontains=q))
	if status:
		qs = qs.filter(status=status)
	if category:
		qs = qs.filter(category=category)
	if branch_id is not None:
		qs = qs.filter(branch_id=branch_id)

	context = {
		"quotations": qs[:50],
		"counts": {
			"draft": qs.filter(status=Quotation.Status.DRAFT).count(),
			"sent": qs.filter(status=Quotation.Status.SENT).count(),
			"approved": qs.filter(status=Quotation.Status.ACCEPTED).count(),
			"expired": qs.filter(status=Quotation.Status.EXPIRED).count(),
		},
		"branches": Branch.objects.filter(is_active=True),
		"status_choices": Quotation.Status.choices,
		"category_choices": Quotation.Category.choices,
		"filters": {"q": q, "status": status, "category": category, "branch": _get_str(request, "branch")},
		"qs": _current_querystring(request),
	}
	return render(request, "modules/quotations.html", context)


@login_required
def add_quotation(request):
	from sales.forms import QuotationForm
	from sales.models import Quotation

	if request.method == "POST":
		form = QuotationForm(request.POST)
		if form.is_valid():
			quote: Quotation = form.save(commit=False)
			quote.created_by = request.user
			quote.status = Quotation.Status.DRAFT
			quote.save()
			# initial totals
			quote.recalculate_amounts(save=True)
			messages.success(request, "Quotation created.")
			return redirect("quotation_detail", quotation_id=quote.id)
	else:
		form = QuotationForm()

	return render(request, "modules/add_quotation.html", {"form": form})


@login_required
def edit_quotation(request, quotation_id: int):
	from sales.forms import QuotationForm
	from sales.models import Quotation

	quote = get_object_or_404(Quotation.objects.select_related("client"), pk=quotation_id)
	if quote.status in {Quotation.Status.CONVERTED}:
		messages.warning(request, "Converted quotations are read-only.")
		return redirect("quotation_detail", quotation_id=quote.id)

	if request.method == "POST":
		form = QuotationForm(request.POST, instance=quote)
		if form.is_valid():
			form.save()
			quote.recalculate_amounts(save=True)
			messages.success(request, "Quotation updated.")
			return redirect("quotation_detail", quotation_id=quote.id)
	else:
		form = QuotationForm(instance=quote)

	return render(request, "modules/edit_quotation.html", {"form": form, "quotation": quote})


@login_required
def quotation_detail(request, quotation_id: int):
	from sales.models import Quotation
	from documents.models import Document

	quote = get_object_or_404(Quotation.objects.select_related("client", "created_by"), pk=quotation_id)
	# Avoid writes on GET (and avoid production-only DB edge cases). If these
	# computations fail, still render the page with stored values.
	try:
		quote.refresh_expiry_status(save=False)
		quote.recalculate_amounts(save=False)
	except Exception:
		pass

	docs = Document.objects.filter(related_quotation=quote).order_by("-uploaded_at", "-version")
	return render(
		request,
		"modules/quotation_detail.html",
		{
			"quotation": quote,
			"badge": _quotation_badge_class,
			"documents": docs[:20],
		},
	)


@login_required
def add_quotation_item(request, quotation_id: int):
	from sales.forms import QuotationItemForm
	from sales.models import Quotation, QuotationItem

	quote = get_object_or_404(Quotation.objects.select_related("client"), pk=quotation_id)
	if quote.status in {Quotation.Status.CONVERTED}:
		messages.warning(request, "Converted quotations are read-only.")
		return redirect("quotation_detail", quotation_id=quote.id)

	if request.method == "POST":
		form = QuotationItemForm(request.POST)
		if form.is_valid():
			item: QuotationItem = form.save(commit=False)
			item.quotation = quote
			item.save()
			messages.success(request, "Item added.")
			return redirect("quotation_detail", quotation_id=quote.id)
	else:
		form = QuotationItemForm()

	return render(request, "modules/add_quotation_item.html", {"form": form, "quotation": quote})


@login_required
def edit_quotation_item(request, quotation_id: int, item_id: int):
	from sales.forms import QuotationItemForm
	from sales.models import Quotation, QuotationItem

	quote = get_object_or_404(Quotation, pk=quotation_id)
	item = get_object_or_404(QuotationItem, pk=item_id, quotation=quote)
	if quote.status in {Quotation.Status.CONVERTED}:
		messages.warning(request, "Converted quotations are read-only.")
		return redirect("quotation_detail", quotation_id=quote.id)

	if request.method == "POST":
		form = QuotationItemForm(request.POST, instance=item)
		if form.is_valid():
			form.save()
			messages.success(request, "Item updated.")
			return redirect("quotation_detail", quotation_id=quote.id)
	else:
		form = QuotationItemForm(instance=item)

	return render(request, "modules/edit_quotation_item.html", {"form": form, "quotation": quote, "item": item})


@login_required
def delete_quotation_item(request, quotation_id: int, item_id: int):
	from sales.models import Quotation, QuotationItem

	quote = get_object_or_404(Quotation, pk=quotation_id)
	item = get_object_or_404(QuotationItem, pk=item_id, quotation=quote)
	if quote.status in {Quotation.Status.CONVERTED}:
		messages.warning(request, "Converted quotations are read-only.")
		return redirect("quotation_detail", quotation_id=quote.id)

	if request.method == "POST":
		item.delete()
		messages.success(request, "Item deleted.")
		return redirect("quotation_detail", quotation_id=quote.id)
	return redirect("quotation_detail", quotation_id=quote.id)


@login_required
def set_quotation_status(request, quotation_id: int, status: str):
	from sales.models import Quotation
	from core.audit import log_event
	from core.models import AuditEvent

	quote = get_object_or_404(Quotation, pk=quotation_id)
	allowed = {Quotation.Status.SENT, Quotation.Status.ACCEPTED, Quotation.Status.REJECTED}
	if request.method != "POST":
		return redirect("quotation_detail", quotation_id=quote.id)
	if status not in allowed:
		messages.error(request, "Invalid status change.")
		return redirect("quotation_detail", quotation_id=quote.id)
	if quote.status in {Quotation.Status.CONVERTED}:
		messages.warning(request, "Converted quotations are read-only.")
		return redirect("quotation_detail", quotation_id=quote.id)
	if quote.status == Quotation.Status.EXPIRED:
		messages.warning(request, "Expired quotations cannot be updated.")
		return redirect("quotation_detail", quotation_id=quote.id)

	old_status = quote.status
	quote.status = status
	quote.save(update_fields=["status"])
	log_event(
		action=AuditEvent.Action.QUOTATION_STATUS_CHANGED,
		actor=request.user,
		entity=quote,
		client=quote.client,
		summary=f"{quote.number}: {old_status} -> {status}",
		meta={"from": old_status, "to": status},
	)
	messages.success(request, "Quotation status updated.")
	return redirect("quotation_detail", quotation_id=quote.id)


def _build_quotation_pdf_bytes(quote, *, proforma: bool = False) -> bytes:
	from reportlab.lib.units import mm

	buffer = BytesIO()
	title = f"Proforma {quote.number}" if proforma else f"Quotation {quote.number}"
	doc = SimpleDocTemplate(
		buffer,
		pagesize=A4,
		title=title,
		topMargin=90,
		bottomMargin=72,
	)
	styles = getSampleStyleSheet()

	client_name = str(quote.client)
	client_email = getattr(quote.client, "email", "") or "-"
	valid_until = quote.valid_until.isoformat() if quote.valid_until else "-"
	prepared_by = (getattr(quote.created_by, "email", "") if quote.created_by else "") or "-"

	elements = [
		Paragraph(title, styles["Title"]),
		Spacer(1, 6),
		Paragraph(f"Client: {client_name}", styles["Normal"]),
		Paragraph(f"Email: {client_email}", styles["Normal"]),
		Paragraph(f"Category: {quote.category_label}", styles["Normal"]),
		Paragraph(f"Valid until: {valid_until}", styles["Normal"]),
		Paragraph(f"Prepared by: {prepared_by}", styles["Normal"]),
		Spacer(1, 10),
	]

	items = list(quote.items.all())
	rows: list[list[str]] = []
	for it in items:
		rows.append([
			(it.item_name or it.description or "-")[:60],
			str(it.quantity),
			_money(it.unit_price),
			_money(it.line_total()),
		])
	if not rows:
		rows = [["(No items)", "-", "-", "-"]]

	data = [["Item", "Qty", "Unit Price", "Line Total"]] + rows
	table = Table(data, repeatRows=1, colWidths=[90 * mm, 20 * mm, 35 * mm, 35 * mm])
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
				("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	elements.append(table)

	discount = (quote.discount_amount or Decimal("0.00")).quantize(Decimal("0.01"))
	elements += [
		Spacer(1, 10),
		Paragraph(f"Subtotal: {quote.currency} {_money(quote.subtotal())}", styles["Normal"]),
	]
	if discount > Decimal("0.00"):
		elements.append(Paragraph(f"Discount: {quote.currency} {_money(discount)}", styles["Normal"]))
	if quote.vat_enabled:
		elements.append(Paragraph(f"VAT ({quote.vat_rate * 100:.0f}%): {quote.currency} {_money(quote.vat_amount())}", styles["Normal"]))
	else:
		elements.append(Paragraph("VAT: Not applied", styles["Normal"]))
	elements.append(Paragraph(f"Total: {quote.currency} {_money(quote.total())}", styles["Heading3"]))

	if quote.notes:
		elements += [Spacer(1, 8), Paragraph("Notes:", styles["Heading4"]), Paragraph(quote.notes, styles["Normal"])]

	doc.build(
		elements,
		onFirstPage=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
		onLaterPages=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
	)
	pdf_bytes = buffer.getvalue()
	buffer.close()
	return pdf_bytes


@login_required
def quotation_pdf(request, quotation_id: int):
	from sales.models import Quotation
	quote = get_object_or_404(Quotation.objects.select_related("client", "created_by"), pk=quotation_id)
	pdf_bytes = _build_quotation_pdf_bytes(quote, proforma=False)
	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	response["Content-Disposition"] = f'attachment; filename="{quote.number}.pdf"'
	return response


@login_required
def proforma_pdf(request, quotation_id: int):
	from sales.models import Quotation
	quote = get_object_or_404(Quotation.objects.select_related("client", "created_by"), pk=quotation_id)
	pdf_bytes = _build_quotation_pdf_bytes(quote, proforma=True)
	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	response["Content-Disposition"] = f'attachment; filename="PROFORMA-{quote.number}.pdf"'
	return response


@login_required
def send_quotation(request, quotation_id: int):
	"""Send quotation PDF to the client email (explicit action)."""
	from django.conf import settings
	from django.core.mail import EmailMultiAlternatives
	from django.core.files.base import ContentFile
	from sales.models import Quotation
	from documents.models import Document

	quote = get_object_or_404(Quotation.objects.select_related("client", "created_by"), pk=quotation_id)
	if request.method != "POST":
		return redirect("quotation_detail", quotation_id=quote.id)

	client_email = getattr(quote.client, "email", "")
	client_email = (client_email or "").strip()
	if not client_email:
		messages.error(request, "Client does not have an email address.")
		return redirect("quotation_detail", quotation_id=quote.id)

	pdf_bytes = _build_quotation_pdf_bytes(quote, proforma=False)
	subject = f"Quotation {quote.number}"
	body = (
		f"Dear {quote.client},\n\n"
		f"Please find attached Quotation {quote.number}.\n\n"
		"Regards,\nJambas Imaging"
	)
	msg = EmailMultiAlternatives(
		subject=subject,
		body=body,
		from_email=settings.DEFAULT_FROM_EMAIL,
		to=[client_email],
	)
	msg.attach(filename=f"{quote.number}.pdf", content=pdf_bytes, mimetype="application/pdf")
	try:
		msg.send(fail_silently=False)
		Document.objects.create(
			branch_id=getattr(quote, "branch_id", None),
			client=quote.client,
			related_quotation=quote,
			related_invoice_id=getattr(getattr(quote, "invoice", None), "id", None),
			doc_type=Document.DocumentType.QUOTATION,
			title=f"Quotation {quote.number}",
			uploaded_by=request.user,
			file=ContentFile(pdf_bytes, name=f"{quote.number}.pdf"),
		)
		messages.success(request, "Quotation sent to client.")
	except Exception:
		messages.error(request, "Failed to send quotation email. Check email settings.")
	return redirect("quotation_detail", quotation_id=quote.id)


@login_required
def convert_quotation_to_invoice(request, quotation_id: int):
	from sales.models import Quotation
	from invoices.models import Invoice, InvoiceItem

	quote = get_object_or_404(Quotation.objects.select_related("client"), pk=quotation_id)
	if request.method != "POST":
		return redirect("quotation_detail", quotation_id=quote.id)
	quote.refresh_expiry_status(save=True)
	if quote.status != Quotation.Status.ACCEPTED:
		messages.error(request, "Only Approved quotations can be converted to an invoice.")
		return redirect("quotation_detail", quotation_id=quote.id)
	if hasattr(quote, "invoice") and quote.invoice_id:
		return redirect("invoice_detail", invoice_id=quote.invoice_id)

	invoice = Invoice.objects.create(
		client=quote.client,
		quotation=quote,
		created_by=request.user,
		currency=quote.currency,
		vat_rate=(quote.vat_rate if quote.vat_enabled else Decimal("0.00")),
		notes=(quote.notes or ""),
		prepared_by_name=getattr(request.user, "email", "") or str(request.user),
	)
	for it in quote.items.all():
		InvoiceItem.objects.create(
			invoice=invoice,
			product=it.product,
			description=(it.item_name or it.description or "Item"),
			quantity=it.quantity,
			unit_price=it.unit_price,
		)
	if (quote.discount_amount or Decimal("0.00")) > Decimal("0.00"):
		InvoiceItem.objects.create(
			invoice=invoice,
			description="Discount",
			quantity=Decimal("1.00"),
			unit_price=(Decimal("0.00") - quote.discount_amount).quantize(Decimal("0.01")),
		)

	quote.status = Quotation.Status.CONVERTED
	quote.save(update_fields=["status"])
	messages.success(request, "Quotation converted to invoice.")
	return redirect("invoice_detail", invoice_id=invoice.id)


def _money(val) -> str:
	try:
		return f"{val:,.2f}"
	except Exception:
		return str(val)


_COMPANY_FOOTER_LINE_1 = (
	"JAMBAS IMAGING (U) LTD - Integrated solutions in printing, branding, IT products, "
	"IT support services, safety gears, medical supplies, and stationery."
)
_COMPANY_FOOTER_LINE_2 = "+256 200 902 849  |   info@jambasimaging.com  |   F-26, Nasser Road Mall, Kampala – Uganda"


def _pdf_branding_static_paths() -> tuple[str | None, str | None]:
	"""Return (svg_logo_path, png_logo_path) if available via staticfiles finders."""
	try:
		from django.contrib.staticfiles import finders
		svg_path = finders.find("images/jambas-logo-white.svg")
		png_path = finders.find("images/jambas-company-logo.png")
		return svg_path, png_path
	except Exception:
		return None, None


def _pdf_draw_header_footer(canvas, doc, *, title: str) -> None:
	"""Draw a branded header/footer on each PDF page."""
	from reportlab.platypus import Frame, Paragraph
	from reportlab.lib.styles import ParagraphStyle

	page_width, page_height = doc.pagesize
	left = doc.leftMargin
	right = page_width - doc.rightMargin

	bar_h = 62
	canvas.saveState()

	# Header bar (blue) + white logo
	canvas.setFillColor(colors.HexColor("#0d6efd"))
	canvas.rect(0, page_height - bar_h, page_width, bar_h, fill=1, stroke=0)

	svg_path, png_path = _pdf_branding_static_paths()
	logo_drawn = False
	logo_x = left
	logo_y = page_height - bar_h + 14
	logo_w = 210
	logo_h = 34
	if svg_path:
		try:
			from svglib.svglib import svg2rlg
			from reportlab.graphics import renderPDF
			drawing = svg2rlg(svg_path)
			if drawing and getattr(drawing, "width", 0) and getattr(drawing, "height", 0):
				scale = min(logo_w / float(drawing.width), logo_h / float(drawing.height))
				drawing.scale(scale, scale)
				renderPDF.draw(drawing, canvas, logo_x, logo_y)
				logo_drawn = True
		except Exception:
			logo_drawn = False
	if (not logo_drawn) and png_path:
		try:
			canvas.drawImage(png_path, logo_x, logo_y, width=logo_h, height=logo_h, mask="auto")
			logo_drawn = True
		except Exception:
			pass

	# Document title on the right
	canvas.setFillColor(colors.white)
	canvas.setFont("Helvetica-Bold", 13)
	canvas.drawRightString(right, page_height - 24, title)

	# Footer
	canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
	canvas.setLineWidth(0.6)
	canvas.line(left, 58, right, 58)

	footer_style = ParagraphStyle(
		"pdf_footer",
		fontName="Helvetica",
		fontSize=8,
		leading=9,
		textColor=colors.HexColor("#334155"),
		alignment=1,
	)
	footer_frame = Frame(left, 18, right - left, 34, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
	footer_frame.addFromList(
		[
			Paragraph(_COMPANY_FOOTER_LINE_1, footer_style),
			Paragraph(_COMPANY_FOOTER_LINE_2, footer_style),
		],
		canvas,
	)

	canvas.restoreState()


def _build_invoice_pdf_bytes(invoice) -> bytes:
	"""Generate a simple PDF invoice (for email/download)."""
	from reportlab.lib.units import mm

	buffer = BytesIO()
	title = f"Invoice {invoice.number}"
	doc = SimpleDocTemplate(
		buffer,
		pagesize=A4,
		title=title,
		topMargin=90,
		bottomMargin=72,
	)
	styles = getSampleStyleSheet()

	client_name = str(invoice.client)
	client_email = getattr(invoice.client, "email", "") or "-"
	issued = invoice.issued_at.isoformat() if invoice.issued_at else "-"
	due = invoice.due_at.isoformat() if invoice.due_at else "-"
	prepared_by = (invoice.prepared_by_name or "").strip() or (getattr(invoice.created_by, "email", "") if invoice.created_by else "") or "-"
	signed_by = (invoice.signed_by_name or "").strip() or "-"
	signed_at = timezone.localtime(invoice.signed_at).strftime("%Y-%m-%d %H:%M") if invoice.signed_at else "-"

	elements = [
		Paragraph(f"Invoice {invoice.number}", styles["Title"]),
		Spacer(1, 6),
		Paragraph(f"Client: {client_name}", styles["Normal"]),
		Paragraph(f"Email: {client_email}", styles["Normal"]),
		Paragraph(f"Issued: {issued} &nbsp;&nbsp; Due: {due}", styles["Normal"]),
		Paragraph(f"Prepared by: {prepared_by}", styles["Normal"]),
		Paragraph(f"Signed by: {signed_by} &nbsp;&nbsp; Signed at: {signed_at}", styles["Normal"]),
		Spacer(1, 10),
	]

	items = list(invoice.items.all())
	rows: list[list[str]] = []
	for it in items:
		rows.append([
			(it.description or "-")[:60],
			str(it.quantity),
			_money(it.unit_price),
			_money(it.line_total()),
		])

	if not rows:
		rows = [["(No items)", "-", "-", "-"]]

	data = [["Description", "Qty", "Unit Price", "Line Total"]] + rows
	table = Table(data, repeatRows=1, colWidths=[90 * mm, 20 * mm, 35 * mm, 35 * mm])
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
				("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	elements.append(table)

	elements += [
		Spacer(1, 10),
		Paragraph(f"Subtotal: {invoice.currency} {_money(invoice.subtotal())}", styles["Normal"]),
		Paragraph(f"VAT ({invoice.vat_rate * 100:.0f}%): {invoice.currency} {_money(invoice.vat_amount())}", styles["Normal"]),
		Paragraph(f"Total: {invoice.currency} {_money(invoice.total())}", styles["Heading3"]),
	]
	if invoice.notes:
		elements += [Spacer(1, 8), Paragraph("Notes:", styles["Heading4"]), Paragraph(invoice.notes, styles["Normal"])]

	doc.build(
		elements,
		onFirstPage=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
		onLaterPages=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
	)
	pdf_bytes = buffer.getvalue()
	buffer.close()
	return pdf_bytes


def _build_receipt_pdf_bytes(payment) -> bytes:
	"""Generate a simple receipt PDF for a payment."""
	invoice = payment.invoice
	buffer = BytesIO()
	title = f"Receipt {payment.receipt_number}"
	doc = SimpleDocTemplate(
		buffer,
		pagesize=A4,
		title=title,
		topMargin=90,
		bottomMargin=72,
	)
	styles = getSampleStyleSheet()

	paid_at = timezone.localtime(payment.paid_at).strftime("%Y-%m-%d %H:%M")

	elements = [
		Paragraph(f"Receipt {payment.receipt_number}", styles["Title"]),
		Spacer(1, 8),
		Paragraph(f"Invoice: {invoice.number}", styles["Normal"]),
		Paragraph(f"Client: {invoice.client}", styles["Normal"]),
		Paragraph(f"Paid at: {paid_at}", styles["Normal"]),
		Paragraph(f"Method: {payment.method_label}", styles["Normal"]),
		Paragraph(f"Reference: {payment.reference or '-'}", styles["Normal"]),
		Spacer(1, 12),
	]

	data = [
		["Description", "Amount"],
		["Payment", f"{invoice.currency} {_money(payment.amount)}"],
		["Invoice Total", f"{invoice.currency} {_money(invoice.total())}"],
		["Total Paid", f"{invoice.currency} {_money(invoice.amount_paid())}"],
		["Outstanding", f"{invoice.currency} {_money(invoice.outstanding_balance())}"],
	]
	table = Table(data, repeatRows=1)
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
				("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
				("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	elements.append(table)

	if payment.notes:
		elements += [Spacer(1, 10), Paragraph("Notes:", styles["Heading4"]), Paragraph(payment.notes, styles["Normal"])]

	doc.build(
		elements,
		onFirstPage=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
		onLaterPages=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
	)
	pdf_bytes = buffer.getvalue()
	buffer.close()
	return pdf_bytes


@login_required
def invoice_detail(request, invoice_id: int):
	from invoices.models import Invoice
	from invoices.forms import InvoiceSignatureForm, PaymentForm
	from documents.models import Document

	invoice = (
		Invoice.objects.select_related("client", "branch")
		.prefetch_related("items", "payments")
		.get(pk=invoice_id)
	)

	invoice_docs = Document.objects.filter(related_invoice=invoice).order_by("-uploaded_at", "-version")
	receipt_docs = Document.objects.filter(
		related_payment_id__in=list(invoice.payments.values_list("id", flat=True))
	).order_by("-uploaded_at", "-version")
	receipt_doc_by_payment_id = {d.related_payment_id: d for d in receipt_docs if d.related_payment_id}
	for p in invoice.payments.all():
		p.archived_receipt_doc = receipt_doc_by_payment_id.get(p.id)

	payment_form = PaymentForm(invoice=invoice)
	signature_form = InvoiceSignatureForm(initial={"name": invoice.signed_by_name or ""})
	context = {
		"invoice": invoice,
		"items": invoice.items.all(),
		"payments": invoice.payments.all(),
		"invoice_documents": invoice_docs[:20],
		"payment_form": payment_form,
		"signature_form": signature_form,
		"totals": {
			"subtotal": invoice.subtotal(),
			"vat": invoice.vat_amount(),
			"total": invoice.total(),
			"paid": invoice.amount_paid(),
			"balance": invoice.outstanding_balance(),
		},
	}
	return render(request, "modules/invoice_detail.html", context)


@login_required
def sign_invoice(request, invoice_id: int):
	from invoices.models import Invoice
	from invoices.forms import InvoiceSignatureForm

	invoice = Invoice.objects.get(pk=invoice_id)
	if request.method != "POST":
		return redirect("invoice_detail", invoice_id=invoice_id)

	form = InvoiceSignatureForm(request.POST)
	if form.is_valid():
		name = (form.cleaned_data["name"] or "").strip()
		invoice.signed_by_name = name
		invoice.signed_at = timezone.now() if name else None
		invoice.save(update_fields=["signed_by_name", "signed_at"])
		messages.success(request, "Invoice signed.")
	return redirect("invoice_detail", invoice_id=invoice_id)


@login_required
def add_invoice_item(request, invoice_id: int):
	from invoices.models import Invoice
	from invoices.forms import InvoiceItemForm

	invoice = Invoice.objects.select_related("client").get(pk=invoice_id)
	if request.method == "POST":
		form = InvoiceItemForm(request.POST)
		if form.is_valid():
			item = form.save(commit=False)
			item.invoice = invoice
			item.save()
			invoice.refresh_status_from_payments(save=True)
			messages.success(request, "Invoice item added.")
			return redirect("invoice_detail", invoice_id=invoice_id)
	else:
		form = InvoiceItemForm()

	return render(request, "modules/add_invoice_item.html", {"invoice": invoice, "form": form})


@login_required
def edit_invoice_item(request, invoice_id: int, item_id: int):
	from invoices.models import Invoice, InvoiceItem
	from invoices.forms import InvoiceItemForm

	invoice = Invoice.objects.select_related("client").get(pk=invoice_id)
	item = InvoiceItem.objects.get(pk=item_id, invoice_id=invoice_id)
	if request.method == "POST":
		form = InvoiceItemForm(request.POST, instance=item)
		if form.is_valid():
			form.save()
			invoice.refresh_status_from_payments(save=True)
			messages.success(request, "Invoice item updated.")
			return redirect("invoice_detail", invoice_id=invoice_id)
	else:
		form = InvoiceItemForm(instance=item)

	return render(request, "modules/edit_invoice_item.html", {"invoice": invoice, "item": item, "form": form})


@login_required
def delete_invoice_item(request, invoice_id: int, item_id: int):
	from invoices.models import Invoice, InvoiceItem

	if request.method != "POST":
		return redirect("invoice_detail", invoice_id=invoice_id)

	invoice = Invoice.objects.get(pk=invoice_id)
	InvoiceItem.objects.filter(pk=item_id, invoice_id=invoice_id).delete()
	invoice.refresh_status_from_payments(save=True)
	messages.success(request, "Invoice item deleted.")
	return redirect("invoice_detail", invoice_id=invoice_id)


@login_required
def add_invoice_payment(request, invoice_id: int):
	from invoices.models import Invoice
	from invoices.forms import PaymentForm

	invoice = Invoice.objects.select_related("client").get(pk=invoice_id)
	if request.method != "POST":
		return redirect("invoice_detail", invoice_id=invoice_id)

	form = PaymentForm(request.POST, invoice=invoice)
	if form.is_valid():
		payment = form.save(commit=False)
		payment.recorded_by = request.user
		payment.save()
		messages.success(request, "Payment recorded.")
		return redirect("invoice_detail", invoice_id=invoice_id)

	# Re-render detail page with errors
	context = {
		"invoice": invoice,
		"items": invoice.items.all(),
		"payments": invoice.payments.all(),
		"payment_form": form,
		"totals": {
			"subtotal": invoice.subtotal(),
			"vat": invoice.vat_amount(),
			"total": invoice.total(),
			"paid": invoice.amount_paid(),
			"balance": invoice.outstanding_balance(),
		},
	}
	return render(request, "modules/invoice_detail.html", context)


@login_required
def payment_receipt_pdf(request, invoice_id: int, payment_id: int):
	from invoices.models import Payment

	payment = Payment.objects.select_related("invoice", "invoice__client").get(pk=payment_id, invoice_id=invoice_id)
	pdf_bytes = _build_receipt_pdf_bytes(payment)
	filename = f"receipt-{payment.receipt_number or payment.pk}.pdf"
	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	response["Content-Disposition"] = f'attachment; filename="{filename}"'
	return response


@login_required
def send_payment_receipt(request, invoice_id: int, payment_id: int):
	"""Email a receipt PDF for a specific payment (explicit action)."""
	from django.conf import settings
	from django.core.mail import EmailMultiAlternatives
	from django.core.files.base import ContentFile
	from invoices.models import Payment
	from documents.models import Document

	if request.method != "POST":
		return redirect("invoice_detail", invoice_id=invoice_id)

	payment = Payment.objects.select_related("invoice", "invoice__client").get(pk=payment_id, invoice_id=invoice_id)
	client_email = getattr(payment.invoice.client, "email", "")
	client_email = (client_email or "").strip()
	if not client_email:
		messages.error(request, "Client does not have an email address.")
		return redirect("invoice_detail", invoice_id=invoice_id)

	pdf_bytes = _build_receipt_pdf_bytes(payment)
	subject = f"Receipt {payment.receipt_number or payment.pk} for Invoice {payment.invoice.number}"
	body = (
		f"Dear {payment.invoice.client},\n\n"
		f"Please find attached the receipt for Invoice {payment.invoice.number}.\n"
		f"Receipt: {payment.receipt_number or payment.pk}\n"
		f"Amount: {payment.invoice.currency} {_money(payment.amount)}\n"
		f"Paid at: {timezone.localtime(payment.paid_at).strftime('%Y-%m-%d %H:%M')}\n\n"
		"Regards,\nJambas Imaging"
	)

	msg = EmailMultiAlternatives(
		subject=subject,
		body=body,
		from_email=settings.DEFAULT_FROM_EMAIL,
		to=[client_email],
	)
	filename = f"receipt-{payment.receipt_number or payment.pk}.pdf"
	msg.attach(filename=filename, content=pdf_bytes, mimetype="application/pdf")
	try:
		msg.send(fail_silently=False)
		Document.objects.create(
			branch_id=getattr(payment.invoice, "branch_id", None),
			client=payment.invoice.client,
			related_quotation_id=getattr(payment.invoice, "quotation_id", None),
			related_invoice=payment.invoice,
			related_payment=payment,
			doc_type=Document.DocumentType.RECEIPT,
			title=f"Receipt {payment.receipt_number or payment.pk} ({payment.invoice.number})",
			uploaded_by=request.user,
			file=ContentFile(pdf_bytes, name=filename),
		)
		messages.success(request, "Receipt sent to client.")
	except Exception:
		messages.error(request, "Failed to send receipt email. Check email settings.")
	return redirect("invoice_detail", invoice_id=invoice_id)


@login_required
def invoice_pdf(request, invoice_id: int):
	from invoices.models import Invoice

	invoice = Invoice.objects.select_related("client").prefetch_related("items", "payments").get(pk=invoice_id)
	pdf_bytes = _build_invoice_pdf_bytes(invoice)
	filename = f"invoice-{invoice.number}.pdf"
	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	response["Content-Disposition"] = f'attachment; filename="{filename}"'
	return response


@login_required
def send_invoice(request, invoice_id: int):
	"""Send invoice to client email with PDF attached."""
	from django.conf import settings
	from django.core.mail import EmailMultiAlternatives
	from django.core.files.base import ContentFile
	from django.template.loader import render_to_string
	from documents.models import Document

	from invoices.models import Invoice

	invoice = Invoice.objects.select_related("client").prefetch_related("items").get(pk=invoice_id)
	client_email = getattr(invoice.client, "email", "")
	if request.method != "POST":
		return redirect("invoice_detail", invoice_id=invoice_id)

	if not client_email:
		messages.error(request, "Client does not have an email address.")
		return redirect("invoice_detail", invoice_id=invoice_id)

	context = {"invoice": invoice}
	subject = f"Invoice {invoice.number}"
	text_body = render_to_string("invoices/invoice_email.txt", context)
	html_body = render_to_string("invoices/invoice_email.html", context)

	msg = EmailMultiAlternatives(subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[client_email])
	msg.attach_alternative(html_body, "text/html")

	pdf_bytes = _build_invoice_pdf_bytes(invoice)
	filename = f"invoice-{invoice.number}.pdf"
	msg.attach(filename=filename, content=pdf_bytes, mimetype="application/pdf")
	try:
		msg.send(fail_silently=False)
		Document.objects.create(
			branch_id=getattr(invoice, "branch_id", None),
			client=invoice.client,
			related_quotation_id=getattr(invoice, "quotation_id", None),
			related_invoice=invoice,
			doc_type=Document.DocumentType.INVOICE,
			title=f"Invoice {invoice.number}",
			uploaded_by=request.user,
			file=ContentFile(pdf_bytes, name=filename),
		)
		messages.success(request, f"Invoice sent to {client_email}.")
	except Exception:
		messages.error(request, "Failed to send invoice email. Check email settings.")
	return redirect("invoice_detail", invoice_id=invoice_id)


@login_required
def export_invoices_csv(request):
	"""Download invoices as CSV."""
	from invoices.models import Invoice

	response = HttpResponse(content_type="text/csv")
	response["Content-Disposition"] = 'attachment; filename="invoices.csv"'

	writer = csv.writer(response)
	writer.writerow(["Number", "Client", "Status", "Issued", "Due", "Created"]) 
	qs = Invoice.objects.select_related("client", "branch").all().order_by("-created_at")
	qs = _filter_invoices(request, qs)
	for inv in qs:
		writer.writerow([
			inv.number,
			str(inv.client),
			inv.status,
			inv.issued_at.isoformat() if inv.issued_at else "",
			inv.due_at.isoformat() if inv.due_at else "",
			inv.created_at.date().isoformat(),
		])
	return response


@login_required
def export_invoices_pdf(request):
	"""Download invoices as PDF."""
	from invoices.models import Invoice

	rows: list[list[str]] = []
	qs = Invoice.objects.select_related("client", "branch").all().order_by("-created_at")
	qs = _filter_invoices(request, qs)
	for inv in qs[:200]:
		rows.append([
			(inv.number or "-")[:20],
			(str(inv.client) or "-")[:35],
			inv.status,
			inv.issued_at.isoformat() if inv.issued_at else "-",
			inv.due_at.isoformat() if inv.due_at else "-",
		])

	return _pdf_response(
		title="Invoices",
		header=["Number", "Client", "Status", "Issued", "Due"],
		rows=rows,
		filename="invoices.pdf",
	)


@login_required
def inventory_view(request):
	"""Inventory frontend page (UI only)."""
	from inventory.models import Product

	from core.models import Branch
	from inventory.models import ProductCategory, Supplier

	products_qs = Product.objects.select_related("category", "supplier", "branch").all()
	products_qs = _filter_inventory(request, products_qs)
	# Keep performance high: compute low stock via ORM, not Python loops.
	low_stock_count = products_qs.filter(stock_quantity__lte=F("low_stock_threshold")).count()

	context = {
		"products": products_qs[:50],
		"products_total": products_qs.count(),
		"products_low_stock": low_stock_count,
		"branches": Branch.objects.filter(is_active=True),
		"categories": ProductCategory.objects.all().order_by("name"),
		"suppliers": Supplier.objects.all().order_by("name"),
		"filters": {
			"q": _get_str(request, "q"),
			"branch": _get_str(request, "branch"),
			"category": _get_str(request, "category"),
			"supplier": _get_str(request, "supplier"),
			"low_stock": "1" if _get_bool(request, "low_stock") else "",
			"is_active": _get_str(request, "is_active"),
		},
		"qs": _current_querystring(request),
	}
	return render(request, "modules/inventory.html", context)


def suppliers_view(request):
	"""Suppliers register (list + filters)."""
	from inventory.models import Supplier

	q = (request.GET.get("q") or "").strip()
	is_active = (request.GET.get("is_active") or "").strip()

	qs = Supplier.objects.all().order_by("name")
	if q:
		qs = qs.filter(name__icontains=q)
	if is_active in {"0", "1"}:
		qs = qs.filter(is_active=(is_active == "1"))

	context = {
		"suppliers": qs,
		"filters": {"q": q, "is_active": is_active},
	}
	return render(request, "modules/suppliers.html", context)


def add_supplier(request):
	from inventory.forms import SupplierForm

	if request.method == "POST":
		form = SupplierForm(request.POST)
		if form.is_valid():
			form.save()
			return redirect("suppliers")
	else:
		form = SupplierForm()

	return render(request, "modules/add_supplier.html", {"form": form})


def edit_supplier(request, supplier_id: int):
	from inventory.forms import SupplierForm
	from inventory.models import Supplier

	supplier = get_object_or_404(Supplier, pk=supplier_id)
	if request.method == "POST":
		form = SupplierForm(request.POST, instance=supplier)
		if form.is_valid():
			form.save()
			return redirect("supplier_detail", supplier_id=supplier.id)
	else:
		form = SupplierForm(instance=supplier)

	return render(request, "modules/edit_supplier.html", {"form": form, "supplier": supplier})


def supplier_detail(request, supplier_id: int):
	from inventory.models import Supplier, SupplierProductPrice

	supplier = get_object_or_404(Supplier, pk=supplier_id)
	prices = (
		SupplierProductPrice.objects.select_related("product")
		.filter(supplier=supplier)
		.order_by("-quoted_at", "-id")
	)

	return render(
		request,
		"modules/supplier_detail.html",
		{
			"supplier": supplier,
			"prices": prices,
		},
	)


def add_supplier_price(request):
	"""Capture supplier pricing for a product.

	Accepts optional query params: ?supplier=<id>&product=<id>
	"""
	from inventory.forms import SupplierProductPriceForm
	from inventory.models import Supplier, Product

	initial = {}
	supplier_id = request.GET.get("supplier")
	product_id = request.GET.get("product")
	if supplier_id:
		try:
			initial["supplier"] = Supplier.objects.get(pk=int(supplier_id))
		except Exception:
			pass
	if product_id:
		try:
			initial["product"] = Product.objects.get(pk=int(product_id))
		except Exception:
			pass

	if request.method == "POST":
		form = SupplierProductPriceForm(request.POST)
		if form.is_valid():
			price = form.save()
			# Prefer returning back to supplier detail if supplier was specified.
			return redirect("supplier_detail", supplier_id=price.supplier_id)
	else:
		form = SupplierProductPriceForm(initial=initial)

	return render(request, "modules/add_supplier_price.html", {"form": form})


def product_price_compare(request, product_id: int):
	"""Compare supplier prices for a single product."""
	from inventory.models import Product, SupplierProductPrice

	product = get_object_or_404(Product, pk=product_id)
	all_prices = (
		SupplierProductPrice.objects.select_related("supplier")
		.filter(product=product, is_active=True)
		.order_by("-quoted_at", "unit_price")
	)

	# Pick latest record per supplier (sqlite-friendly, done in Python)
	latest_by_supplier = {}
	for p in all_prices:
		if p.supplier_id not in latest_by_supplier:
			latest_by_supplier[p.supplier_id] = p
	latest_prices = sorted(latest_by_supplier.values(), key=lambda x: (x.unit_price, x.supplier.name.lower()))

	return render(
		request,
		"modules/product_prices.html",
		{
			"product": product,
			"prices": latest_prices,
		},
	)


@login_required
def add_inventory(request):
	"""Create a product (inventory item) via a server-rendered ModelForm."""
	from inventory.forms import ProductForm

	if request.method == "POST":
		form = ProductForm(request.POST)
		if form.is_valid():
			form.save()
			return redirect("inventory")
	else:
		form = ProductForm()

	return render(request, "modules/add_inventory.html", {"form": form})


@login_required
def export_inventory_csv(request):
	"""Download inventory products as CSV."""
	from inventory.models import Product

	response = HttpResponse(content_type="text/csv")
	response["Content-Disposition"] = 'attachment; filename="inventory.csv"'

	writer = csv.writer(response)
	writer.writerow(["SKU", "Name", "Category", "Supplier", "Unit Price", "Stock", "Low Stock Threshold"]) 
	qs = Product.objects.select_related("category", "supplier", "branch").all().order_by("name")
	qs = _filter_inventory(request, qs)
	for p in qs:
		writer.writerow([
			p.sku,
			p.name,
			str(p.category),
			str(p.supplier) if p.supplier else "",
			str(p.unit_price),
			str(p.stock_quantity),
			str(p.low_stock_threshold),
		])
	return response


@login_required
def export_inventory_pdf(request):
	"""Download inventory products as PDF."""
	from inventory.models import Product

	rows: list[list[str]] = []
	qs = Product.objects.select_related("category", "supplier", "branch").all().order_by("name")
	qs = _filter_inventory(request, qs)
	for p in qs[:200]:
		rows.append([
			(p.sku or "-")[:16],
			(p.name or "-")[:32],
			(str(p.category) or "-")[:18],
			(str(p.stock_quantity) or "-")[:12],
			("LOW" if p.stock_quantity <= p.low_stock_threshold else "OK"),
		])

	return _pdf_response(
		title="Inventory",
		header=["SKU", "Name", "Category", "Stock", "Status"],
		rows=rows,
		filename="inventory.pdf",
	)


@login_required
def expenses_view(request):
	from django.db.models import Sum

	from core.models import Branch
	from expenses.models import Expense

	expenses_qs = Expense.objects.select_related("branch", "created_by").all()
	expenses_qs = _filter_expenses(request, expenses_qs)

	total_amount = expenses_qs.aggregate(total=Sum("amount")).get("total") or 0

	context = {
		"expenses": expenses_qs[:50],
		"expenses_total": expenses_qs.count(),
		"expenses_amount": total_amount,
		"branches": Branch.objects.filter(is_active=True),
		"category_choices": Expense.Category.choices,
		"filters": {
			"q": _get_str(request, "q"),
			"branch": _get_str(request, "branch"),
			"category": _get_str(request, "category"),
			"from": _get_str(request, "from"),
			"to": _get_str(request, "to"),
		},
		"qs": _current_querystring(request),
	}
	return render(request, "modules/expenses.html", context)


@login_required
def add_expense(request):
	from expenses.forms import ExpenseForm

	if request.method == "POST":
		form = ExpenseForm(request.POST)
		if form.is_valid():
			expense = form.save(commit=False)
			expense.created_by = request.user
			expense.save()
			messages.success(request, "Expense recorded.")
			return redirect("expenses")
	else:
		form = ExpenseForm()

	return render(request, "modules/add_expense.html", {"form": form})


@login_required
def export_expenses_csv(request):
	from expenses.models import Expense

	response = HttpResponse(content_type="text/csv")
	response["Content-Disposition"] = 'attachment; filename="expenses.csv"'
	writer = csv.writer(response)
	writer.writerow(["Date", "Branch", "Category", "Description", "Amount", "Reference"]) 

	qs = Expense.objects.select_related("branch").all()
	qs = _filter_expenses(request, qs)
	for e in qs:
		writer.writerow([
			e.expense_date.isoformat(),
			str(e.branch) if e.branch else "",
			e.category,
			e.description,
			str(e.amount),
			e.reference,
		])
	return response


@login_required
def export_expenses_pdf(request):
	from expenses.models import Expense

	rows: list[list[str]] = []
	qs = Expense.objects.select_related("branch").all()
	qs = _filter_expenses(request, qs)
	for e in qs[:200]:
		rows.append([
			e.expense_date.isoformat(),
			(str(e.branch) if e.branch else "-")[:18],
			e.category,
			(e.description or "-")[:40],
			str(e.amount),
		])

	return _pdf_response(
		title="Expenses",
		header=["Date", "Branch", "Category", "Description", "Amount"],
		rows=rows,
		filename="expenses.pdf",
	)


@login_required
def appointments_view(request):
	"""Appointments frontend page (UI only)."""
	from appointments.models import Appointment

	from core.models import Branch

	appointments_qs = Appointment.objects.select_related("client", "assigned_to", "branch").all()
	appointments_qs = _filter_appointments(request, appointments_qs)
	now = timezone.now()
	context = {
		"appointments": appointments_qs[:50],
		"appointments_total": appointments_qs.count(),
		"appointments_upcoming": appointments_qs.filter(scheduled_for__gte=now).count(),
		"appointments_pending": appointments_qs.filter(status=Appointment.Status.PENDING).count(),
		"branches": Branch.objects.filter(is_active=True),
		"status_choices": Appointment.Status.choices,
		"type_choices": Appointment.AppointmentType.choices,
		"filters": {
			"q": _get_str(request, "q"),
			"status": _get_str(request, "status"),
			"appointment_type": _get_str(request, "appointment_type"),
			"branch": _get_str(request, "branch"),
			"from": _get_str(request, "from"),
			"to": _get_str(request, "to"),
		},
		"qs": _current_querystring(request),
	}
	return render(request, "modules/appointments.html", context)


@login_required
def add_appointment(request):
	"""Create an appointment via a server-rendered ModelForm.

	- `created_by` is set from the logged-in user.
	"""
	from appointments.forms import AppointmentForm

	if request.method == "POST":
		form = AppointmentForm(request.POST)
		if form.is_valid():
			appt = form.save(commit=False)
			appt.created_by = request.user
			appt.save()
			return redirect("appointments")
	else:
		form = AppointmentForm()

	return render(request, "modules/add_appointment.html", {"form": form})


@login_required
def export_appointments_csv(request):
	"""Download appointments as CSV."""
	from appointments.models import Appointment

	response = HttpResponse(content_type="text/csv")
	response["Content-Disposition"] = 'attachment; filename="appointments.csv"'

	writer = csv.writer(response)
	writer.writerow(["Scheduled For", "Client", "Type", "Status", "Assigned To"]) 
	qs = Appointment.objects.select_related("client", "assigned_to", "branch").all().order_by("-scheduled_for")
	qs = _filter_appointments(request, qs)
	for a in qs:
		writer.writerow([
			a.scheduled_for.isoformat(sep=" ", timespec="minutes"),
			str(a.client),
			a.appointment_type,
			a.status,
			(a.assigned_to.email if a.assigned_to else ""),
		])
	return response


@login_required
def export_appointments_pdf(request):
	"""Download appointments as PDF."""
	from appointments.models import Appointment

	rows: list[list[str]] = []
	qs = Appointment.objects.select_related("client", "assigned_to", "branch").all().order_by("-scheduled_for")
	qs = _filter_appointments(request, qs)
	for a in qs[:200]:
		rows.append([
			a.scheduled_for.strftime("%Y-%m-%d %H:%M"),
			(str(a.client) or "-")[:28],
			a.appointment_type,
			a.status,
			(a.assigned_to.email if a.assigned_to else "-")[:24],
		])

	return _pdf_response(
		title="Appointments",
		header=["Scheduled", "Client", "Type", "Status", "Assigned"],
		rows=rows,
		filename="appointments.pdf",
	)


@login_required
def reports_view(request):
	"""Reports frontend page (UI only)."""
	from appointments.models import Appointment
	from clients.models import Client
	from core.models import Branch
	from django.db.models import Sum
	from inventory.models import Product
	from invoices.models import Invoice
	from invoices.models import Payment
	from expenses.models import Expense

	now = timezone.now()

	# Optional report filters
	branch_id = _get_int(request, "branch")
	from_date = _get_date(request, "from")
	to_date = _get_date(request, "to")

	clients_qs = Client.objects.all()
	invoices_qs = Invoice.objects.all()
	payments_qs = Payment.objects.select_related("invoice").all()
	expenses_qs = Expense.objects.all()
	appointments_qs = Appointment.objects.all()
	products_qs = Product.objects.all()
	if branch_id is not None:
		clients_qs = clients_qs.filter(branch_id=branch_id)
		invoices_qs = invoices_qs.filter(branch_id=branch_id)
		payments_qs = payments_qs.filter(invoice__branch_id=branch_id)
		expenses_qs = expenses_qs.filter(branch_id=branch_id)
		appointments_qs = appointments_qs.filter(branch_id=branch_id)
		products_qs = products_qs.filter(branch_id=branch_id)
	if from_date:
		invoices_qs = invoices_qs.filter(created_at__date__gte=from_date)
		clients_qs = clients_qs.filter(created_at__date__gte=from_date)
		payments_qs = payments_qs.filter(paid_at__date__gte=from_date)
		expenses_qs = expenses_qs.filter(expense_date__gte=from_date)
		appointments_qs = appointments_qs.filter(created_at__date__gte=from_date)
		products_qs = products_qs.filter(created_at__date__gte=from_date)
	if to_date:
		invoices_qs = invoices_qs.filter(created_at__date__lte=to_date)
		clients_qs = clients_qs.filter(created_at__date__lte=to_date)
		payments_qs = payments_qs.filter(paid_at__date__lte=to_date)
		expenses_qs = expenses_qs.filter(expense_date__lte=to_date)
		appointments_qs = appointments_qs.filter(created_at__date__lte=to_date)
		products_qs = products_qs.filter(created_at__date__lte=to_date)

	clients_total = clients_qs.count()
	clients_active = clients_qs.filter(status=Client.Status.ACTIVE).count()
	invoices_total = invoices_qs.count()
	invoices_paid = invoices_qs.filter(status=Invoice.Status.PAID).count()
	show_income = _can_view_income(request.user)
	revenue_total = payments_qs.aggregate(total=Sum("amount")).get("total") or 0 if show_income else None
	expenses_total = expenses_qs.aggregate(total=Sum("amount")).get("total") or 0
	net_profit = (revenue_total - expenses_total) if show_income else None
	appointments_upcoming = appointments_qs.filter(scheduled_for__gte=now).count()
	products_total = products_qs.count()
	products_low_stock = products_qs.filter(stock_quantity__lte=F("low_stock_threshold")).count()

	context = {
		"kpis": {
			"clients_total": clients_total,
			"clients_active": clients_active,
			"invoices_total": invoices_total,
			"invoices_paid": invoices_paid,
			"revenue_total": revenue_total,
			"expenses_total": expenses_total,
			"net_profit": net_profit,
			"products_total": products_total,
			"products_low_stock": products_low_stock,
			"appointments_upcoming": appointments_upcoming,
		},
		"show_income": show_income,
		"branches": Branch.objects.filter(is_active=True),
		"filters": {
			"branch": _get_str(request, "branch"),
			"from": _get_str(request, "from"),
			"to": _get_str(request, "to"),
		},
		"qs": _current_querystring(request),
	}
	return render(request, "modules/reports.html", context)


@login_required
def export_reports_csv(request):
	"""Download report KPI summary as CSV (respects report filters)."""
	# Reuse reports_view calculations by duplicating the same filtered QS logic.
	from appointments.models import Appointment
	from clients.models import Client
	from django.db.models import Sum
	from inventory.models import Product
	from invoices.models import Invoice
	from invoices.models import Payment
	from expenses.models import Expense

	now = timezone.now()
	branch_id = _get_int(request, "branch")
	from_date = _get_date(request, "from")
	to_date = _get_date(request, "to")

	clients_qs = Client.objects.all()
	invoices_qs = Invoice.objects.all()
	payments_qs = Payment.objects.select_related("invoice").all()
	expenses_qs = Expense.objects.all()
	appointments_qs = Appointment.objects.all()
	products_qs = Product.objects.all()
	if branch_id is not None:
		clients_qs = clients_qs.filter(branch_id=branch_id)
		invoices_qs = invoices_qs.filter(branch_id=branch_id)
		payments_qs = payments_qs.filter(invoice__branch_id=branch_id)
		expenses_qs = expenses_qs.filter(branch_id=branch_id)
		appointments_qs = appointments_qs.filter(branch_id=branch_id)
		products_qs = products_qs.filter(branch_id=branch_id)
	if from_date:
		invoices_qs = invoices_qs.filter(created_at__date__gte=from_date)
		clients_qs = clients_qs.filter(created_at__date__gte=from_date)
		payments_qs = payments_qs.filter(paid_at__date__gte=from_date)
		expenses_qs = expenses_qs.filter(expense_date__gte=from_date)
		appointments_qs = appointments_qs.filter(created_at__date__gte=from_date)
		products_qs = products_qs.filter(created_at__date__gte=from_date)
	if to_date:
		invoices_qs = invoices_qs.filter(created_at__date__lte=to_date)
		clients_qs = clients_qs.filter(created_at__date__lte=to_date)
		payments_qs = payments_qs.filter(paid_at__date__lte=to_date)
		expenses_qs = expenses_qs.filter(expense_date__lte=to_date)
		appointments_qs = appointments_qs.filter(created_at__date__lte=to_date)
		products_qs = products_qs.filter(created_at__date__lte=to_date)

	response = HttpResponse(content_type="text/csv")
	response["Content-Disposition"] = 'attachment; filename="reports.csv"'
	writer = csv.writer(response)
	writer.writerow(["Metric", "Value"]) 
	writer.writerow(["Clients Total", clients_qs.count()])
	writer.writerow(["Clients Active", clients_qs.filter(status=Client.Status.ACTIVE).count()])
	writer.writerow(["Invoices Total", invoices_qs.count()])
	writer.writerow(["Invoices Paid", invoices_qs.filter(status=Invoice.Status.PAID).count()])
	show_income = _can_view_income(request.user)
	revenue_total = payments_qs.aggregate(total=Sum("amount")).get("total") or 0 if show_income else None
	expenses_total = expenses_qs.aggregate(total=Sum("amount")).get("total") or 0
	if show_income:
		writer.writerow(["Revenue (Payments)", revenue_total])
	writer.writerow(["Expenses", expenses_total])
	if show_income:
		writer.writerow(["Net Profit", revenue_total - expenses_total])
	writer.writerow(["Appointments Upcoming", appointments_qs.filter(scheduled_for__gte=now).count()])
	writer.writerow(["Products Total", products_qs.count()])
	writer.writerow(["Products Low Stock", products_qs.filter(stock_quantity__lte=F("low_stock_threshold")).count()])
	return response


@login_required
def export_reports_pdf(request):
	"""Download report KPI summary as PDF (respects report filters)."""
	from appointments.models import Appointment
	from clients.models import Client
	from django.db.models import Sum
	from inventory.models import Product
	from invoices.models import Invoice
	from invoices.models import Payment
	from expenses.models import Expense

	now = timezone.now()
	branch_id = _get_int(request, "branch")
	from_date = _get_date(request, "from")
	to_date = _get_date(request, "to")

	clients_qs = Client.objects.all()
	invoices_qs = Invoice.objects.all()
	payments_qs = Payment.objects.select_related("invoice").all()
	expenses_qs = Expense.objects.all()
	appointments_qs = Appointment.objects.all()
	products_qs = Product.objects.all()
	if branch_id is not None:
		clients_qs = clients_qs.filter(branch_id=branch_id)
		invoices_qs = invoices_qs.filter(branch_id=branch_id)
		payments_qs = payments_qs.filter(invoice__branch_id=branch_id)
		expenses_qs = expenses_qs.filter(branch_id=branch_id)
		appointments_qs = appointments_qs.filter(branch_id=branch_id)
		products_qs = products_qs.filter(branch_id=branch_id)
	if from_date:
		invoices_qs = invoices_qs.filter(created_at__date__gte=from_date)
		clients_qs = clients_qs.filter(created_at__date__gte=from_date)
		payments_qs = payments_qs.filter(paid_at__date__gte=from_date)
		expenses_qs = expenses_qs.filter(expense_date__gte=from_date)
		appointments_qs = appointments_qs.filter(created_at__date__gte=from_date)
		products_qs = products_qs.filter(created_at__date__gte=from_date)
	if to_date:
		invoices_qs = invoices_qs.filter(created_at__date__lte=to_date)
		clients_qs = clients_qs.filter(created_at__date__lte=to_date)
		payments_qs = payments_qs.filter(paid_at__date__lte=to_date)
		expenses_qs = expenses_qs.filter(expense_date__lte=to_date)
		appointments_qs = appointments_qs.filter(created_at__date__lte=to_date)
		products_qs = products_qs.filter(created_at__date__lte=to_date)

	show_income = _can_view_income(request.user)
	revenue_total = payments_qs.aggregate(total=Sum("amount")).get("total") or 0 if show_income else None
	expenses_total = expenses_qs.aggregate(total=Sum("amount")).get("total") or 0

	rows = [
		["Clients Total", str(clients_qs.count())],
		["Clients Active", str(clients_qs.filter(status=Client.Status.ACTIVE).count())],
		["Invoices Total", str(invoices_qs.count())],
		["Invoices Paid", str(invoices_qs.filter(status=Invoice.Status.PAID).count())],
		["Expenses", str(expenses_total)],
		["Appointments Upcoming", str(appointments_qs.filter(scheduled_for__gte=now).count())],
		["Products Total", str(products_qs.count())],
		["Products Low Stock", str(products_qs.filter(stock_quantity__lte=F("low_stock_threshold")).count())],
	]
	if show_income:
		rows.insert(4, ["Revenue (Payments)", str(revenue_total)])
		rows.insert(6, ["Net Profit", str(revenue_total - expenses_total)])
	return _pdf_response(
		title="Reports Summary",
		header=["Metric", "Value"],
		rows=rows,
		filename="reports.pdf",
	)


@login_required
def users_view(request):
	guard = _require_admin(request)
	if guard is not None:
		return guard

	User = get_user_model()
	users = User.objects.all().order_by("email")
	return render(request, "modules/users.html", {"users": users})


@login_required
def add_user(request):
	guard = _require_admin(request)
	if guard is not None:
		return guard

	from accounts.forms import AdminUserCreateForm

	form = AdminUserCreateForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "User created successfully.")
		return redirect("users")
	return render(request, "modules/add_user.html", {"form": form})


@login_required
def edit_user(request, user_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard

	from accounts.forms import AdminUserUpdateForm

	User = get_user_model()
	user_obj = User.objects.filter(id=user_id).first()
	if user_obj is None:
		messages.error(request, "User not found.")
		return redirect("users")

	form = AdminUserUpdateForm(request.POST or None, instance=user_obj)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "User updated successfully.")
		return redirect("users")
	return render(request, "modules/edit_user.html", {"form": form, "user_obj": user_obj})


@login_required
def audit_logs_view(request):
	guard = _require_admin(request)
	if guard is not None:
		return guard

	from accounts.models import LoginAuditLog
	from core.models import AuditEvent

	try:
		events = AuditEvent.objects.select_related("actor", "client").order_by("-created_at")[:200]
	except Exception:
		events = []
		messages.warning(request, "Audit events are temporarily unavailable.")
	try:
		logins = LoginAuditLog.objects.select_related("user").order_by("-created_at")[:200]
	except Exception:
		logins = []
		messages.warning(request, "Login audit is temporarily unavailable.")
	return render(request, "modules/audit_logs.html", {"events": events, "logins": logins})


# Backwards-compatible alias (older code referenced `dashboard`)
dashboard = dashboard_view
