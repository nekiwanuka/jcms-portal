import csv
from datetime import date as _date
from datetime import datetime as _datetime
from io import BytesIO
from urllib.parse import urlencode
from decimal import Decimal
import os
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


_PDF_FONTS_READY = False
_PDF_BASE_FONT = "Helvetica"
_PDF_BASE_FONT_BOLD = "Helvetica-Bold"


class _BottomAlignedFlowables(Flowable):
	"""Draw a list of flowables bottom-aligned within the remaining frame.

	If the block can't fit in the remaining space, it falls back to normal
	flow so the content can naturally move/split across pages.
	"""

	def __init__(self, flowables):
		super().__init__()
		self.flowables = list(flowables or [])
		self._wrapped = []
		self._padding = 0

	def wrap(self, availWidth, availHeight):
		self._wrapped = []
		total_h = 0
		for flowable in self.flowables:
			w, h = flowable.wrap(availWidth, availHeight)
			self._wrapped.append((flowable, w, h))
			total_h += h
		self._padding = max(0, availHeight - total_h)
		return availWidth, total_h + self._padding

	def split(self, availWidth, availHeight):
		# If we don't fit, let ReportLab handle page flow/splitting normally.
		return self.flowables

	def draw(self):
		y = self._padding
		# Draw from top to bottom in the given order.
		total_h = sum(h for _, _, h in self._wrapped)
		cursor = y + total_h
		for flowable, _, h in self._wrapped:
			cursor -= h
			flowable.drawOn(self.canv, 0, cursor)


def _pdf_setup_fonts(styles=None) -> tuple[str, str]:
	"""Register preferred fonts once and optionally apply to a stylesheet.

	Prefers Arial on Windows; falls back to Helvetica.
	"""
	global _PDF_FONTS_READY, _PDF_BASE_FONT, _PDF_BASE_FONT_BOLD
	if not _PDF_FONTS_READY:
		try:
			windir = os.environ.get("WINDIR", r"C:\\Windows")
			fonts_dir = Path(windir) / "Fonts"
			arial = fonts_dir / "arial.ttf"
			arial_bold = fonts_dir / "arialbd.ttf"
			if arial.exists() and arial_bold.exists():
				pdfmetrics.registerFont(TTFont("Arial", str(arial)))
				pdfmetrics.registerFont(TTFont("Arial-Bold", str(arial_bold)))
				_PDF_BASE_FONT = "Arial"
				_PDF_BASE_FONT_BOLD = "Arial-Bold"
		except Exception:
			pass
		_PDF_FONTS_READY = True

	if styles is not None:
		try:
			styles["Normal"].fontName = _PDF_BASE_FONT
			styles["Heading3"].fontName = _PDF_BASE_FONT_BOLD
			styles["Title"].fontName = _PDF_BASE_FONT_BOLD
		except Exception:
			pass
	return _PDF_BASE_FONT, _PDF_BASE_FONT_BOLD


def _role(user) -> str | None:
	return getattr(user, "role", None)


def _is_admin(user) -> bool:
	return bool(
		user
		and user.is_authenticated
		and (getattr(user, "is_superuser", False) or _role(user) in {"admin", "managing_director"})
	)


def _can_view_income(user) -> bool:
	return bool(
		user
		and user.is_authenticated
		and (getattr(user, "is_superuser", False) or _role(user) in {"admin", "managing_director", "manager"})
	)


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


def _pdf_response(
	title: str,
	header: list[str],
	rows: list[list[str]],
	filename: str,
	*,
	inline: bool = False,
	landscape_mode: bool = False,
) -> HttpResponse:
	"""Generate a simple, reliable PDF table export.

	Uses ReportLab (already in requirements) for cPanel-friendly PDF creation.
	"""
	buffer = BytesIO()
	page_size = landscape(A4) if landscape_mode else A4
	doc = SimpleDocTemplate(
		buffer,
		pagesize=page_size,
		title=title,
		topMargin=90,
		bottomMargin=72,
		leftMargin=36,
		rightMargin=36,
	)
	styles = getSampleStyleSheet()
	base_font, base_font_bold = _pdf_setup_fonts(styles)
	cell_style = ParagraphStyle(
		"pdf_table_cell",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=7.5,
		leading=9,
		textColor=colors.HexColor("#0f172a"),
		wordWrap="CJK",
		splitLongWords=1,
	)
	header_cell_style = ParagraphStyle(
		"pdf_table_header_cell",
		parent=styles["Normal"],
		fontName=base_font_bold,
		fontSize=8.5,
		leading=10,
		textColor=colors.white,
		wordWrap="CJK",
		splitLongWords=1,
	)
	styles.add(
		ParagraphStyle(
			"pdf_export_hint",
			parent=styles["Normal"],
			fontName=base_font,
			fontSize=9,
			leading=11,
			textColor=colors.HexColor("#475569"),
		)
	)

	elements = [
		Paragraph(title, styles["Title"]),
		Spacer(1, 6),
		Paragraph("Generated export", styles["pdf_export_hint"]),
		Spacer(1, 10),
	]

	def _cell_text(value) -> str:
		if value is None:
			return ""
		return str(value)

	def _cell_para(value, *, is_header: bool = False):
		text = _cell_text(value)
		# Preserve a visible placeholder for empty cells.
		if not text:
			text = "-"
		# Escape a few characters that might be interpreted as markup.
		text = (
			text.replace("&", "&amp;")
			.replace("<", "&lt;")
			.replace(">", "&gt;")
			.replace("\n", "<br/>")
		)
		return Paragraph(text, header_cell_style if is_header else cell_style)

	def _looks_numeric(text: str) -> bool:
		# Accept comma-grouped numbers and decimals.
		# Examples: 1,000  1000  1,000.50  -2500.00
		t = (text or "").strip()
		if not t:
			return False
		t = t.replace(",", "")
		# Strip a leading currency label if present (e.g. "UGX 1,000").
		parts = t.split()
		if len(parts) == 2 and all(ch.isalpha() for ch in parts[0]):
			t = parts[1]
		try:
			float(t)
			return True
		except Exception:
			return False

	# Auto-size columns based on content (first N rows for performance).
	sample_rows = rows[:200] if rows else []
	col_count = len(header)
	max_lens = [len(_cell_text(h)) for h in header]
	for r in sample_rows:
		for idx in range(min(col_count, len(r))):
			max_lens[idx] = max(max_lens[idx], len(_cell_text(r[idx])))

	# Weight wide text columns a bit more (description/name/client/title).
	wide_headers = {"description", "details", "name", "client", "title"}
	weights: list[float] = []
	for idx, h in enumerate(header):
		base = min(max_lens[idx], 42)
		hn = (h or "").strip().lower()
		if hn in wide_headers:
			base *= 1.4
		# Explicit tuning for common table exports.
		# Keep ID compact and give Name extra room so values stay on one line.
		if hn == "id":
			base *= 0.7
		elif hn == "name":
			base *= 1.2
		elif hn == "email":
			base *= 1.15
		weights.append(max(6.0, float(base)))
	wsum = sum(weights) or 1.0
	col_widths = [(w / wsum) * float(doc.width) for w in weights]

	# Right-align numeric columns.
	numeric_headers = {
		"amount",
		"total",
		"unit price",
		"price",
		"value",
		"vat",
		"profit",
		"revenue",
		"balance",
		"stock",
		"reorder level",
	}
	numeric_cols: set[int] = set()
	for idx, h in enumerate(header):
		hn = (h or "").strip().lower()
		if hn in numeric_headers:
			numeric_cols.add(idx)
			continue
		# Heuristic: if most of the sampled values look numeric, align right.
		num_like = 0
		seen = 0
		for r in sample_rows:
			if idx >= len(r):
				continue
			seen += 1
			if _looks_numeric(_cell_text(r[idx])):
				num_like += 1
		if seen >= 5 and (num_like / max(seen, 1)) >= 0.8:
			numeric_cols.add(idx)

	data = [[_cell_para(h, is_header=True) for h in header]]
	for r in rows:
		row_cells = []
		for idx in range(len(header)):
			row_cells.append(_cell_para(r[idx] if idx < len(r) else ""))
		data.append(row_cells)
	table = Table(data, repeatRows=1, colWidths=col_widths)
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 8.5),
				("FONTNAME", (0, 1), (-1, -1), base_font),
				("FONTSIZE", (0, 1), (-1, -1), 7.5),
				("ALIGN", (0, 0), (-1, 0), "LEFT"),
				("LEFTPADDING", (0, 0), (-1, -1), 4),
				("RIGHTPADDING", (0, 0), (-1, -1), 4),
				("TOPPADDING", (0, 0), (-1, -1), 2.5),
				("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
				("GRID", (0, 0), (-1, -1), 0.6, colors.black),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)
	for idx in sorted(numeric_cols):
		table.setStyle(TableStyle([("ALIGN", (idx, 1), (idx, -1), "RIGHT")]))

	elements.append(table)
	doc.build(
		elements,
		onFirstPage=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
		onLaterPages=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
	)

	pdf_bytes = buffer.getvalue()
	buffer.close()

	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	disposition = "inline" if inline else "attachment"
	response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
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
		"is_admin": _is_admin(request.user),
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
def edit_client(request, client_id: int):
	from clients.forms import ClientForm
	from clients.models import Client

	client = get_object_or_404(Client, pk=client_id)
	if request.method == "POST":
		form = ClientForm(request.POST, instance=client)
		if form.is_valid():
			form.save()
			messages.success(request, "Client updated.")
			return redirect("client_history", client_id=client.id)
	else:
		form = ClientForm(instance=client)

	return render(request, "modules/edit_client.html", {"form": form, "client": client, "is_admin": _is_admin(request.user)})


@login_required
def delete_client(request, client_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("client_history", client_id=client_id)

	from django.db.models.deletion import ProtectedError
	from clients.models import Client

	client = get_object_or_404(Client, pk=client_id)
	try:
		client.delete()
		messages.success(request, "Client deleted.")
		return redirect("clients")
	except ProtectedError:
		messages.warning(request, "Client is in use and cannot be deleted.")
		return redirect("client_history", client_id=client_id)


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
@xframe_options_sameorigin
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

	extra_inline = _get_str(request, "inline")
	return _pdf_response(
		title="Clients",
		header=["ID", "Type", "Name", "Status", "Phone", "Email"],
		rows=rows,
		filename="clients.pdf",
		inline=extra_inline in {"1", "true", "yes", "on"},
		landscape_mode=True,
	)


@login_required
def client_history(request, client_id: int):
	"""Client history page: show all related business flow records."""
	from clients.models import Client
	from documents.models import Document
	from invoices.models import Invoice, Payment
	from sales.models import Quotation

	client = get_object_or_404(Client, pk=client_id)

	quotations = Quotation.objects.filter(client=client).order_by("-created_at")[:50]
	invoices = Invoice.objects.filter(client=client).order_by("-created_at")[:50]
	invoice_ids = list(invoices.values_list("id", flat=True))
	payments = (
		Payment.objects.select_related("invoice")
		.filter(invoice_id__in=invoice_ids)
		.order_by("-paid_at", "-id")[:100]
	)

	payment_ids = [p.id for p in payments]
	receipt_docs = Document.objects.filter(related_payment_id__in=payment_ids).order_by("-uploaded_at", "-version")
	receipt_doc_by_payment_id = {d.related_payment_id: d for d in receipt_docs if d.related_payment_id}
	for p in payments:
		p.archived_receipt_doc = receipt_doc_by_payment_id.get(p.id)

	documents = Document.objects.filter(client=client).order_by("-uploaded_at", "-version")[:100]

	context = {
		"client": client,
		"quotations": quotations,
		"invoices": invoices,
		"payments": payments,
		"documents": documents,
		"is_admin": _is_admin(request.user),
		"counts": {
			"quotations": Quotation.objects.filter(client=client).count(),
			"invoices": Invoice.objects.filter(client=client).count(),
			"payments": Payment.objects.filter(invoice__client=client).count(),
			"documents": Document.objects.filter(client=client).count(),
		},
	}
	return render(request, "modules/client_history.html", context)


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
		"is_admin": _is_admin(request.user),
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
def edit_invoice(request, invoice_id: int):
	from invoices.forms import InvoiceForm
	from invoices.models import Invoice

	invoice = get_object_or_404(Invoice, pk=invoice_id)
	if invoice.status in {Invoice.Status.PAID, Invoice.Status.CANCELLED}:
		messages.warning(request, "Paid/Cancelled invoices are read-only.")
		return redirect("invoice_detail", invoice_id=invoice.id)

	if request.method == "POST":
		form = InvoiceForm(request.POST, instance=invoice)
		if form.is_valid():
			form.save()
			messages.success(request, "Invoice updated.")
			return redirect("invoice_detail", invoice_id=invoice.id)
	else:
		form = InvoiceForm(instance=invoice)

	return render(request, "modules/edit_invoice.html", {"form": form, "invoice": invoice})


@login_required
def cancel_invoice(request, invoice_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("invoice_detail", invoice_id=invoice_id)

	from invoices.models import Invoice

	invoice = get_object_or_404(Invoice, pk=invoice_id)
	if invoice.status == Invoice.Status.PAID:
		messages.warning(request, "Paid invoices cannot be cancelled. Use refunds instead.")
		return redirect("invoice_detail", invoice_id=invoice.id)

	# Do not allow cancellation if any net payment remains.
	if invoice.amount_paid() > Decimal("0.00"):
		messages.warning(request, "This invoice has payments. Refund/clear payments first, then cancel.")
		return redirect("invoice_detail", invoice_id=invoice.id)

	reason = (request.POST.get("cancel_reason") or "").strip()
	if invoice.status != Invoice.Status.DRAFT and not reason:
		messages.error(request, "Please provide a cancellation reason.")
		return redirect("invoice_detail", invoice_id=invoice.id)

	invoice.status = Invoice.Status.CANCELLED
	invoice.cancel_reason = reason
	invoice.cancelled_at = timezone.now()
	invoice.cancelled_by = request.user
	invoice.save(update_fields=["status", "cancel_reason", "cancelled_at", "cancelled_by"])
	messages.success(request, "Invoice cancelled.")
	return redirect("invoice_detail", invoice_id=invoice.id)


@login_required
def receipts_view(request):
	"""List receipts (payments) with Receipt PDF + Send actions.

	Receipts are per-payment, so this page is effectively a payments/receipts register.
	"""
	from invoices.models import Payment, PaymentRefund
	from documents.models import Document

	payments = list(
		Payment.objects.select_related("invoice", "invoice__client")
		.prefetch_related("refunds")
		.order_by("-paid_at", "-id")
		.all()[:200]
	)
	payment_ids = [p.id for p in payments]
	refunds_qs = PaymentRefund.objects.filter(payment_id__in=payment_ids).only("payment_id", "amount")
	refunds_by_payment_id = {}
	for r in refunds_qs:
		refunds_by_payment_id.setdefault(r.payment_id, []).append(r)
	for p in payments:
		refund_total = sum((r.amount for r in refunds_by_payment_id.get(p.id, [])), Decimal("0.00"))
		p.refunded_total = refund_total
		p.net_amount = (p.amount or Decimal("0.00")) - refund_total
	docs = Document.objects.filter(related_payment_id__in=payment_ids).order_by("-uploaded_at", "-version")
	archived_by_payment_id = {d.related_payment_id: d for d in docs if d.related_payment_id}
	for p in payments:
		p.archived_receipt_doc = archived_by_payment_id.get(p.id)

	return render(request, "modules/receipts.html", {"payments": payments, "is_admin": _is_admin(request.user)})


@login_required
def reverse_receipt(request, payment_id: int):
	"""Reverse a receipt by creating a full refund for the remaining refundable amount."""
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("receipts")

	from decimal import Decimal
	from django.core.exceptions import ValidationError
	from invoices.models import Payment, PaymentRefund

	payment = get_object_or_404(Payment.objects.select_related("invoice", "invoice__client").prefetch_related("refunds"), pk=payment_id)
	reason = (request.POST.get("reverse_reason") or "").strip()
	if not reason:
		messages.error(request, "Please provide a reversal reason.")
		return redirect("receipts")

	already_refunded = sum((r.amount for r in payment.refunds.all()), Decimal("0.00"))
	refundable = (payment.amount or Decimal("0.00")) - already_refunded
	if refundable <= Decimal("0.00"):
		messages.info(request, "This receipt is already fully reversed/refunded.")
		return redirect("receipts")

	refund = PaymentRefund(
		payment=payment,
		invoice=payment.invoice,
		amount=refundable,
		refunded_by=request.user,
		reference=f"Reversal of {payment.receipt_number or payment.id}",
		notes=f"Receipt reversed: {reason}",
	)
	try:
		refund.save()
		messages.success(request, "Receipt reversed (full refund recorded).")
	except ValidationError as e:
		messages.error(request, str(e))
	except Exception:
		messages.error(request, "Failed to reverse receipt.")

	return redirect("receipts")


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
				invoice.prepared_by_name = (
					(request.session.get("prepared_by_name") or "").strip()
					or getattr(request.user, "full_name", "")
					or getattr(request.user, "email", "")
					or str(request.user)
				)
			invoice.save()

			# If invoice is created from an approved quotation, copy items and mark quotation converted.
			if invoice.quotation_id:
				from invoices.models import InvoiceItem
				from sales.models import Quotation
				from bids.models import Bid
				quote = invoice.quotation
				if quote:
					# Enforce: if quotation is linked to bids, only WON bids can be invoiced.
					bids_qs = quote.bids.all()
					bids_exist = bids_qs.exists()
					can_convert = False
					if bids_exist:
						if bids_qs.filter(status=Bid.Status.WON).exists():
							can_convert = True
						else:
							messages.warning(
								request,
								"Quotation is linked to tenders; only WON bids can be converted to invoices.",
							)
					elif quote.status == Quotation.Status.ACCEPTED:
						# Walk-in / non-tender quotations use the existing APPROVED rule.
						can_convert = True

					if can_convert:
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
					elif not bids_exist:
						# Preserve existing message for non-tender quotations.
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
		Quotation.Status.CANCELLED: "text-bg-danger",
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
	if quote.status in {Quotation.Status.CONVERTED, Quotation.Status.CANCELLED}:
		messages.warning(request, "Converted/Cancelled quotations are read-only.")
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
			"is_admin": _is_admin(request.user),
		},
	)


@login_required
def add_quotation_item(request, quotation_id: int):
	from sales.forms import QuotationItemForm
	from sales.models import Quotation, QuotationItem

	quote = get_object_or_404(Quotation.objects.select_related("client"), pk=quotation_id)
	if quote.status in {Quotation.Status.CONVERTED, Quotation.Status.CANCELLED}:
		messages.warning(request, "Converted/Cancelled quotations are read-only.")
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
	if quote.status in {Quotation.Status.CONVERTED, Quotation.Status.CANCELLED}:
		messages.warning(request, "Converted/Cancelled quotations are read-only.")
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
	if quote.status in {Quotation.Status.CONVERTED, Quotation.Status.CANCELLED}:
		messages.warning(request, "Converted/Cancelled quotations are read-only.")
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
	from invoices.models import Invoice

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
	if quote.status == Quotation.Status.CANCELLED:
		messages.warning(request, "Cancelled quotations are read-only.")
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

	# If approving, immediately convert to an invoice (quotation copy still remains).
	if status == Quotation.Status.ACCEPTED:
		existing_invoice_id = Invoice.objects.filter(quotation=quote).values_list("id", flat=True).first()
		if existing_invoice_id:
			return redirect("invoice_detail", invoice_id=existing_invoice_id)
		try:
			invoice = _convert_quotation_to_invoice_internal(quote=quote, actor=request.user)
			log_event(
				action=AuditEvent.Action.QUOTATION_STATUS_CHANGED,
				actor=request.user,
				entity=quote,
				client=quote.client,
				summary=f"{quote.number}: {Quotation.Status.ACCEPTED} -> {Quotation.Status.CONVERTED}",
				meta={"from": Quotation.Status.ACCEPTED, "to": Quotation.Status.CONVERTED},
			)
			messages.success(request, "Quotation approved and converted to invoice.")
			return redirect("invoice_detail", invoice_id=invoice.id)
		except Exception:
			messages.warning(request, "Quotation approved. Conversion failed; use Convert button.")
			return redirect("quotation_detail", quotation_id=quote.id)

	messages.success(request, "Quotation status updated.")
	return redirect("quotation_detail", quotation_id=quote.id)


@login_required
def cancel_quotation(request, quotation_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("quotation_detail", quotation_id=quotation_id)

	from sales.models import Quotation
	from invoices.models import Invoice

	quote = get_object_or_404(Quotation, pk=quotation_id)
	if Invoice.objects.filter(quotation_id=quote.id).exists() or quote.status == Quotation.Status.CONVERTED:
		messages.warning(request, "Converted quotations cannot be cancelled.")
		return redirect("quotation_detail", quotation_id=quote.id)
	if quote.status == Quotation.Status.CANCELLED:
		messages.info(request, "Quotation is already cancelled.")
		return redirect("quotation_detail", quotation_id=quote.id)

	reason = (request.POST.get("cancel_reason") or "").strip()
	if not reason:
		messages.error(request, "Please provide a cancellation reason.")
		return redirect("quotation_detail", quotation_id=quote.id)

	quote.status = Quotation.Status.CANCELLED
	quote.cancel_reason = reason
	quote.cancelled_at = timezone.now()
	quote.cancelled_by = request.user
	quote.save(update_fields=["status", "cancel_reason", "cancelled_at", "cancelled_by"])
	messages.success(request, "Quotation cancelled.")
	return redirect("quotation_detail", quotation_id=quote.id)


def _build_quotation_pdf_bytes(quote, *, proforma: bool = False, issued_by: str | None = None) -> bytes:
	from reportlab.lib.units import mm

	buffer = BytesIO()
	doc_type = "PROFORMA INVOICE" if proforma else "QUOTATION"
	doc = SimpleDocTemplate(
		buffer,
		pagesize=A4,
		title=f"{doc_type} {quote.number}",
		topMargin=90,
		bottomMargin=72,
		leftMargin=36,
		rightMargin=36,
	)
	styles = getSampleStyleSheet()
	base_font, base_font_bold = _pdf_setup_fonts(styles)
	styles["Title"].textColor = colors.HexColor("#0f172a")
	styles.add(
		ParagraphStyle(
			"pdf_section",
			parent=styles["Heading3"],
			textColor=colors.HexColor("#0f172a"),
			spaceBefore=8,
			spaceAfter=4,
		)
	)
	item_style = ParagraphStyle(
		"pdf_item",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=9.5,
		leading=11,
		textColor=colors.HexColor("#0f172a"),
	)
	note_style = ParagraphStyle(
		"pdf_notes",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=10,
		leading=14,
		textColor=colors.HexColor("#0f172a"),
	)

	def _default_notes_html(*, is_proforma: bool) -> str:
		payment = (
			"Payment methods accepted: <b>Bank</b>, <b>Mobile Money</b>, and <b>Cash</b>. "
			"Please quote the document number on all payments for easy tracking."
		)
		sep = "<br/><br/>"
		if is_proforma:
			lines = [
				"• This Proforma Invoice is issued for payment request/confirmation and is not a Tax Invoice.",
				"• Work/production starts after payment is confirmed (and artwork approval where applicable).",
				"• Delivery/lead time starts after payment confirmation.",
				"• VAT is applied where applicable as shown on this document.",
				f"• {payment}",
			]
			return sep.join(lines)
		lines = [
			"• This quotation is valid until the stated <b>Valid until</b> date.",
			"• Prices may change after expiry or if scope/specifications change.",
			"• Work/production starts after confirmation and payment (unless agreed otherwise).",
			"• VAT is applied where applicable as shown on this quotation.",
			f"• {payment}",
		]
		return sep.join(lines)

	client_name = str(quote.client)
	client_email = getattr(quote.client, "email", "") or "-"
	issued_by_name = (issued_by or "").strip()
	if not issued_by_name:
		creator = getattr(quote, "created_by", None)
		issued_by_name = (
			(getattr(creator, "get_full_name", lambda: "")() if creator else "")
			or (getattr(creator, "email", "") if creator else "")
			or "JAMBAS IMAGING (U) LTD"
		)
	quote_date = (
		timezone.localtime(quote.created_at).date().isoformat() if getattr(quote, "created_at", None) else "-"
	)
	valid_until = quote.valid_until.isoformat() if quote.valid_until else "-"

	# Build TO/FROM blocks as flowables.
	blank = ""
	client_obj = getattr(quote, "client", None)
	address = (getattr(client_obj, "physical_address", "") or "").strip()
	contact_person = (getattr(client_obj, "contact_person", "") or "").strip()
	phone = (getattr(client_obj, "phone", "") or "").strip()
	email = (getattr(client_obj, "email", "") or "").strip()
	if phone and email:
		phone_email_line = f"{phone} / {email}"
	elif phone:
		phone_email_line = phone
	elif email:
		phone_email_line = email
	else:
		phone_email_line = blank

	label_style = ParagraphStyle(
		"pdf_kv_label",
		parent=styles["Normal"],
		fontName=base_font_bold,
		fontSize=9,
		leading=11,
		textColor=colors.HexColor("#0f172a"),
	)
	value_style = ParagraphStyle(
		"pdf_kv_value",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=9,
		leading=11,
		textColor=colors.HexColor("#0f172a"),
	)

	def _kv_row(label: str, value: str) -> list[object]:
		label_txt = (label or "").strip().upper() + ":"
		return [Paragraph(label_txt, label_style), Paragraph(value or blank, value_style)]

	# Keep TO compact: each parameter on the same line with its value.
	to_kv = Table(
		[
			_kv_row("Client Name", client_name),
			_kv_row("Address", address),
			_kv_row("Contact Person", contact_person),
			_kv_row("Phone", phone),
			_kv_row("Email", email),
		],
		colWidths=[28 * mm, float(doc.width) * 0.5 - 28 * mm],
	)
	to_kv.setStyle(
		TableStyle(
			[
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 1),
				("RIGHTPADDING", (0, 0), (0, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)
	gutter_w = 14 * mm
	to_w = (float(doc.width) - gutter_w) / 2.0
	from_w = (float(doc.width) - gutter_w) / 2.0
	from_kv = Table(
		[
			_kv_row("Company", "JAMBAS IMAGING (U) LTD"),
			_kv_row("Address", "F-26, Nasser Road Mall, Kampala – Uganda"),
			_kv_row("Tel", "+256 200 902 849"),
			_kv_row("Email", "info@jambasimaging.com"),
			_kv_row("Website", "www.jambasimaging.com"),
		],
		colWidths=[28 * mm, from_w - 28 * mm],
	)
	from_kv.setStyle(
		TableStyle(
			[
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 1),
				("RIGHTPADDING", (0, 0), (0, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)

	to_from_table = Table(
		[
			["TO", "", "FROM"],
			[to_kv, "", from_kv],
		],
		# Span full available width so the blue header bar aligns with other tables.
		colWidths=[to_w, gutter_w, from_w],
	)
	# Style the TO/FROM table: blue header, white text; no vertical separators.
	to_from_table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (0, 0), (0, 0), "LEFT"),
				("ALIGN", (2, 0), (2, 0), "LEFT"),
				("LEFTPADDING", (0, 0), (0, -1), 6),
				("RIGHTPADDING", (0, 0), (0, -1), 6),
				("LEFTPADDING", (1, 0), (1, -1), 0),
				("RIGHTPADDING", (1, 0), (1, -1), 0),
				("LEFTPADDING", (2, 0), (2, -1), 6),
				("RIGHTPADDING", (2, 0), (2, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 6),
				("BOTTOMPADDING", (0, 0), (-1, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
				("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
				("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#0d6efd")),
			]
		)
	)

	meta_table = Table(
		[
			["ISSUED BY", "DATE | VALID UNTIL"],
			[issued_by_name, f"{quote_date} | {valid_until}"],
		],
		colWidths=[doc.width * 0.45, doc.width * 0.55],
	)
	meta_table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (0, 0), (-1, 0), "LEFT"),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)

	# Create header table with document type on left and number on right
	header_table = Table(
		[
			[doc_type, f"No. {quote.number}"],
		],
		colWidths=[doc.width * 0.5, doc.width * 0.5],
	)
	header_table.setStyle(
		TableStyle(
			[
				("ALIGN", (0, 0), (0, 0), "LEFT"),
				("ALIGN", (1, 0), (1, 0), "RIGHT"),
				("FONTNAME", (0, 0), (-1, -1), base_font_bold),
				("FONTSIZE", (0, 0), (-1, -1), 14),
				("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 0),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)

	elements = [
		header_table,
		Spacer(1, 8),
		to_from_table,
		Spacer(1, 20),
		meta_table,
		Spacer(1, 12),
	]

	items = list(quote.items.all())
	rows: list[list[object]] = []
	for it in items:
		item_name = (it.item_name or "-")
		desc = (it.description or "-")
		rows.append(
			[
				Paragraph(str(item_name), item_style),
				Paragraph(str(desc), item_style),
				Paragraph(str(it.quantity), item_style),
				Paragraph(_money(it.unit_price), item_style),
				Paragraph(_money(it.line_total()), item_style),
			]
		)
	if not rows:
		rows = [[Paragraph("(No items)", item_style), "-", "-", "-", "-"]]

	data = [["Item", "Description", "Qty", "Unit Price", "Amount"]] + rows
	item_w = 35 * mm
	qty_w = 25 * mm
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (2, 1), (2, -1), "CENTER"),
				("ALIGN", (3, 1), (4, -1), "RIGHT"),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("GRID", (0, 0), (-1, -1), 0.6, colors.black),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	elements.append(table)

	discount = (quote.discount_amount or Decimal("0.00")).quantize(Decimal("0.01"))
	amount_rows: list[list[str]] = [["Sub total", f"{quote.currency} {_money(quote.subtotal())}"]]
	if discount > Decimal("0.00"):
		amount_rows.append(["Discount", f"{quote.currency} {_money(discount)}"])
	if quote.vat_enabled:
		amount_rows.append(["VAT 18%", f"{quote.currency} {_money(quote.vat_amount())}"])
	else:
		amount_rows.append(["VAT", "Not applied"])
	amount_rows.append(["TOTAL", f"{quote.currency} {_money(quote.total())}"])

	amount_data = [["Summary", "Amount"]] + amount_rows
	amount_table = Table(
		amount_data,
		colWidths=[item_col_widths[2] + item_col_widths[3], item_col_widths[4]],
	)
	amount_table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("GRID", (0, 0), (-1, -1), 0.6, colors.black),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("ALIGN", (0, 1), (0, -1), "LEFT"),
				("ALIGN", (1, 1), (1, -1), "RIGHT"),
				("FONTNAME", (0, 1), (0, -1), base_font_bold),
				("FONTNAME", (0, -1), (-1, -1), base_font_bold),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	amount_wrap = Table(
		[["", amount_table]],
		colWidths=[item_col_widths[0] + item_col_widths[1], item_col_widths[2] + item_col_widths[3] + item_col_widths[4]],
	)
	amount_wrap.setStyle(
		TableStyle(
			[
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 0),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)
	elements += [Spacer(1, 12), amount_wrap]

	notes_text = (quote.notes or "").strip()
	if not notes_text:
		notes_text = _default_notes_html(is_proforma=proforma)
	# Render notes (either user-provided or defaults) at the bottom above the footer.
	elements += [
		Spacer(1, 12),
		_BottomAlignedFlowables(
			[
				Paragraph("Notes / Terms", styles["pdf_section"]),
				Paragraph(notes_text, note_style),
			]
		),
	]

	doc.build(
		elements,
		onFirstPage=lambda c, d: _pdf_draw_header_footer(c, d, title=f"{doc_type} {quote.number}"),
		onLaterPages=lambda c, d: _pdf_draw_header_footer(c, d, title=f"{doc_type} {quote.number}"),
	)
	pdf_bytes = buffer.getvalue()
	buffer.close()
	return pdf_bytes


@login_required
@xframe_options_sameorigin
def quotation_pdf(request, quotation_id: int):
	from sales.models import Quotation
	quote = get_object_or_404(Quotation.objects.select_related("client", "created_by"), pk=quotation_id)
	shift_issued = (request.session.get("issued_by_name") or request.session.get("prepared_by_name") or "").strip() or None
	pdf_bytes = _build_quotation_pdf_bytes(quote, proforma=False, issued_by=shift_issued)
	client_label = str(quote.client).replace(" ", "_")[:40] or "Client"
	filename = f"Quotation_{client_label}_{quote.number}.pdf"
	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	extra_inline = _get_str(request, "inline")
	if extra_inline in {"1", "true", "yes", "on"}:
		response["Content-Disposition"] = f'inline; filename="{filename}"'
	else:
		response["Content-Disposition"] = f'attachment; filename="{filename}"'
	return response


@login_required
@xframe_options_sameorigin
def proforma_pdf(request, quotation_id: int):
	from sales.models import Quotation
	quote = get_object_or_404(Quotation.objects.select_related("client", "created_by"), pk=quotation_id)
	shift_issued = (request.session.get("issued_by_name") or request.session.get("prepared_by_name") or "").strip() or None
	pdf_bytes = _build_quotation_pdf_bytes(quote, proforma=True, issued_by=shift_issued)
	client_label = str(quote.client).replace(" ", "_")[:40] or "Client"
	filename = f"Proforma_{client_label}_{quote.number}.pdf"
	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	extra_inline = _get_str(request, "inline")
	if extra_inline in {"1", "true", "yes", "on"}:
		response["Content-Disposition"] = f'inline; filename="{filename}"'
	else:
		response["Content-Disposition"] = f'attachment; filename="{filename}"'
	return response


@login_required
def send_quotation(request, quotation_id: int):
	"""Send quotation PDF to the client email (explicit action)."""
	from django.conf import settings
	from django.core.mail import EmailMultiAlternatives
	from django.core.files.base import ContentFile
	from sales.models import Quotation
	from invoices.models import Invoice
	from documents.models import Document

	quote = get_object_or_404(Quotation.objects.select_related("client", "created_by"), pk=quotation_id)
	if request.method != "POST":
		return redirect("quotation_detail", quotation_id=quote.id)

	client_email = getattr(quote.client, "email", "")
	client_email = (client_email or "").strip()
	if not client_email:
		messages.error(request, "Client does not have an email address.")
		return redirect("quotation_detail", quotation_id=quote.id)

	shift_issued = (request.session.get("issued_by_name") or request.session.get("prepared_by_name") or "").strip() or None
	pdf_bytes = _build_quotation_pdf_bytes(quote, proforma=False, issued_by=shift_issued)
	client_label = str(quote.client).replace(" ", "_")[:40] or "Client"
	filename = f"Quotation_{client_label}_{quote.number}.pdf"
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
	msg.attach(filename=filename, content=pdf_bytes, mimetype="application/pdf")
	try:
		msg.send(fail_silently=False)
		related_invoice_id = Invoice.objects.filter(quotation=quote).values_list("id", flat=True).first()
		Document.objects.create(
			branch_id=getattr(quote, "branch_id", None),
			client=quote.client,
			related_quotation=quote,
			related_invoice_id=related_invoice_id,
			doc_type=Document.DocumentType.QUOTATION,
			title=f"Quotation {quote.number}",
			uploaded_by=request.user,
			file=ContentFile(pdf_bytes, name=filename),
		)
		messages.success(request, "Quotation sent to client.")
	except Exception:
		messages.error(request, "Failed to send quotation email. Check email settings.")
	return redirect("quotation_detail", quotation_id=quote.id)


@login_required
def convert_quotation_to_invoice(request, quotation_id: int):
	from sales.models import Quotation
	from invoices.models import Invoice

	quote = get_object_or_404(Quotation.objects.select_related("client"), pk=quotation_id)
	if request.method != "POST":
		return redirect("quotation_detail", quotation_id=quote.id)
	quote.refresh_expiry_status(save=True)

	existing_invoice_id = Invoice.objects.filter(quotation=quote).values_list("id", flat=True).first()
	if existing_invoice_id:
		return redirect("invoice_detail", invoice_id=existing_invoice_id)

	if quote.status != Quotation.Status.ACCEPTED:
		messages.error(request, "Only Approved quotations can be converted to an invoice.")
		return redirect("quotation_detail", quotation_id=quote.id)

	invoice = _convert_quotation_to_invoice_internal(quote=quote, actor=request.user)
	messages.success(request, "Quotation converted to invoice.")
	return redirect("invoice_detail", invoice_id=invoice.id)


def _convert_quotation_to_invoice_internal(*, quote, actor):
	"""Create an invoice from an Approved quotation and mark quotation as Converted."""
	from sales.models import Quotation
	from invoices.models import Invoice, InvoiceItem

	if quote.status != Quotation.Status.ACCEPTED:
		raise ValueError("Quotation must be approved before conversion")

	invoice = Invoice.objects.create(
		branch_id=getattr(quote, "branch_id", None),
		client=quote.client,
		quotation=quote,
		created_by=actor,
		currency=quote.currency,
		vat_rate=(quote.vat_rate if quote.vat_enabled else Decimal("0.00")),
		notes=(quote.notes or ""),
		prepared_by_name=getattr(actor, "email", "") or str(actor),
	)
	for it in quote.items.all():
		InvoiceItem.objects.create(
			invoice=invoice,
			product=it.product,
			service=getattr(it, "service", None),
			description=(it.item_name or it.description or "Item"),
			quantity=it.quantity,
			unit_price=it.unit_price,
			vat_exempt=getattr(it, "vat_exempt", False),
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
	return invoice


def _money(val) -> str:
	"""Format monetary amounts consistently across PDFs/exports."""
	try:
		from core.templatetags.formatting import money as money_filter
		return money_filter(val)
	except Exception:
		return str(val)


_COMPANY_FOOTER_LINE_1 = (
	"JAMBAS IMAGING (U) LTD - Integrated solutions in printing, branding, IT products, "
	"IT support services, safety gears, medical supplies, and stationery."
)
_COMPANY_FOOTER_LINE_2 = "+256 200 902 849  |   info@jambasimaging.com  |   F-26, Nasser Road Mall, Kampala – Uganda"

_COMPANY_HEADER_CENTER = "JAMBAS IMAGING (U) LTD"


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
	_pdf_setup_fonts()

	page_width, page_height = doc.pagesize
	left = doc.leftMargin
	right = page_width - doc.rightMargin
	center_x = (left + right) / 2.0

	# Responsive sizing for A4 vs A5 pages.
	bar_h = 62 if page_height >= 750 else 48
	text_font = 12 if page_height >= 750 else 10
	logo_h = 34 if page_height >= 750 else 26
	logo_w = 210 if page_height >= 750 else 160
	footer_line_y = 58 if page_height >= 750 else 44
	bar_y = page_height - bar_h
	text_y = (bar_y + (bar_h / 2.0)) - (text_font * 0.35)
	canvas.saveState()

	# Header bar (blue) + white logo
	canvas.setFillColor(colors.HexColor("#0d6efd"))
	canvas.rect(0, page_height - bar_h, page_width, bar_h, fill=1, stroke=0)

	svg_path, png_path = _pdf_branding_static_paths()
	logo_drawn = False
	logo_x = left
	logo_y = bar_y + ((bar_h - logo_h) / 2.0)
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

	# Company name (center) and document title (right) on the same baseline
	canvas.setFillColor(colors.white)
	canvas.setFont(_PDF_BASE_FONT_BOLD, text_font)
	canvas.drawCentredString(center_x, text_y, _COMPANY_HEADER_CENTER)
	canvas.drawRightString(right, text_y, title)

	# Footer (blue bar with white text)
	footer_h = 44 if page_height >= 750 else 36
	canvas.setFillColor(colors.HexColor("#0d6efd"))
	canvas.rect(0, 0, page_width, footer_h, fill=1, stroke=0)

	footer_style = ParagraphStyle(
		"pdf_footer",
		fontName=_PDF_BASE_FONT,
		fontSize=(8 if page_height >= 750 else 7),
		leading=(9 if page_height >= 750 else 8),
		textColor=colors.white,
		alignment=1,
	)
	footer_bottom = 8
	footer_frame_h = max(18, footer_h - footer_bottom - 4)
	footer_frame = Frame(
		left,
		footer_bottom,
		right - left,
		footer_frame_h,
		leftPadding=0,
		rightPadding=0,
		topPadding=0,
		bottomPadding=0,
		showBoundary=0,
	)
	footer_frame.addFromList(
		[
			Paragraph(_COMPANY_FOOTER_LINE_1, footer_style),
			Paragraph(_COMPANY_FOOTER_LINE_2, footer_style),
		],
		canvas,
	)

	canvas.restoreState()


def _pdf_kv_table(*, styles, left_rows: list[tuple[str, str]], right_rows: list[tuple[str, str]]):
	"""Two-column key/value table for PDFs."""
	base_font, base_font_bold = _pdf_setup_fonts(styles)
	label_style = ParagraphStyle(
		"pdf_kv_label",
		parent=styles["Normal"],
		fontName=base_font_bold,
		fontSize=8.5,
		leading=10,
		textColor=colors.HexColor("#475569"),
	)
	value_style = ParagraphStyle(
		"pdf_kv_value",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=10,
		leading=12,
		textColor=colors.HexColor("#0f172a"),
	)

	max_rows = max(len(left_rows), len(right_rows))
	rows = []
	for i in range(max_rows):
		lk, lv = left_rows[i] if i < len(left_rows) else ("", "")
		rk, rv = right_rows[i] if i < len(right_rows) else ("", "")
		rows.append(
			[
				Paragraph(f"<b>{lk}</b><br/>{lv}", value_style) if lk else "",
				Paragraph(f"<b>{rk}</b><br/>{rv}", value_style) if rk else "",
			]
		)

	t = Table(rows, colWidths=["50%", "50%"])
	t.setStyle(
		TableStyle(
			[
				("GRID", (0, 0), (-1, -1), 0.6, colors.black),
				("LEFTPADDING", (0, 0), (-1, -1), 8),
				("RIGHTPADDING", (0, 0), (-1, -1), 8),
				("TOPPADDING", (0, 0), (-1, -1), 6),
				("BOTTOMPADDING", (0, 0), (-1, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)
	return t


def _build_invoice_pdf_bytes(invoice) -> bytes:
	"""Generate a simple PDF invoice (for email/download)."""
	from reportlab.lib.units import mm

	buffer = BytesIO()
	title = invoice.number
	doc = SimpleDocTemplate(
		buffer,
		pagesize=A4,
		title=title,
		topMargin=90,
		bottomMargin=72,
		leftMargin=36,
		rightMargin=36,
	)
	styles = getSampleStyleSheet()
	base_font, base_font_bold = _pdf_setup_fonts(styles)
	styles["Title"].textColor = colors.HexColor("#0f172a")
	styles.add(
		ParagraphStyle(
			"pdf_section",
			parent=styles["Heading3"],
			textColor=colors.HexColor("#0f172a"),
			spaceBefore=8,
			spaceAfter=4,
		)
	)
	item_style = ParagraphStyle(
		"pdf_item",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=9.5,
		leading=11,
		textColor=colors.HexColor("#0f172a"),
	)

	note_style = ParagraphStyle(
		"pdf_notes",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=10,
		leading=14,
		textColor=colors.HexColor("#0f172a"),
	)

	def _default_notes_html() -> str:
		sep = "<br/><br/>"
		lines = [
			"• Payment is due within stated terms. Late payments may attract penalties.",
			"• Services and reports are released upon payment confirmation.",
			"• Payments are non-refundable once services are rendered.",
			"• This is a system-generated invoice.",
		]
		return sep.join(lines)

	client_name = str(invoice.client)
	client_email = getattr(invoice.client, "email", "") or "-"
	issued = invoice.issued_at.isoformat() if invoice.issued_at else "-"
	due = invoice.due_at.isoformat() if invoice.due_at else "-"
	prepared_by = (invoice.prepared_by_name or "").strip() or (getattr(invoice.created_by, "email", "") if invoice.created_by else "") or "-"
	signed_by = (invoice.signed_by_name or "").strip() or "-"
	signed_at = timezone.localtime(invoice.signed_at).strftime("%Y-%m-%d %H:%M") if invoice.signed_at else "-"

	# Build TO/FROM blocks as flowables.
	blank = ""
	client_obj = getattr(invoice, "client", None)
	address = (getattr(client_obj, "physical_address", "") or "").strip()
	contact_person = (getattr(client_obj, "contact_person", "") or "").strip()
	phone = (getattr(client_obj, "phone", "") or "").strip()
	email = (getattr(client_obj, "email", "") or "").strip()
	if phone and email:
		phone_email_line = f"{phone} / {email}"
	elif phone:
		phone_email_line = phone
	elif email:
		phone_email_line = email
	else:
		phone_email_line = blank

	label_style = ParagraphStyle(
		"pdf_kv_label",
		parent=styles["Normal"],
		fontName=base_font_bold,
		fontSize=9,
		leading=11,
		textColor=colors.HexColor("#0f172a"),
	)
	value_style = ParagraphStyle(
		"pdf_kv_value",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=9,
		leading=11,
		textColor=colors.HexColor("#0f172a"),
	)

	def _kv_row(label: str, value: str) -> list[object]:
		label_txt = (label or "").strip().upper() + ":"
		return [Paragraph(label_txt, label_style), Paragraph(value or blank, value_style)]

	# Keep TO compact: each parameter on the same line with its value.
	to_kv = Table(
		[
			_kv_row("Client Name", client_name),
			_kv_row("Address", address),
			_kv_row("Contact Person", contact_person),
			_kv_row("Phone", phone),
			_kv_row("Email", email),
		],
		colWidths=[28 * mm, float(doc.width) * 0.5 - 28 * mm],
	)
	to_kv.setStyle(
		TableStyle(
			[
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 1),
				("RIGHTPADDING", (0, 0), (0, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)
	gutter_w = 14 * mm
	to_w = (float(doc.width) - gutter_w) / 2.0
	from_w = (float(doc.width) - gutter_w) / 2.0
	from_kv = Table(
		[
			_kv_row("Company", "JAMBAS IMAGING (U) LTD"),
			_kv_row("Address", "F-26, Nasser Road Mall, Kampala – Uganda"),
			_kv_row("Tel", "+256 200 902 849"),
			_kv_row("Email", "info@jambasimaging.com"),
			_kv_row("Website", "www.jambasimaging.com"),
		],
		colWidths=[28 * mm, from_w - 28 * mm],
	)
	from_kv.setStyle(
		TableStyle(
			[
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 1),
				("RIGHTPADDING", (0, 0), (0, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)

	to_from_table = Table(
		[
			["TO", "", "FROM"],
			[to_kv, "", from_kv],
		],
		# Span full available width so the blue header bar aligns with other tables.
		colWidths=[to_w, gutter_w, from_w],
	)
	# Style the TO/FROM table: blue header, white text; no vertical separators.
	to_from_table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (0, 0), (0, 0), "LEFT"),
				("ALIGN", (2, 0), (2, 0), "LEFT"),
				("LEFTPADDING", (0, 0), (0, -1), 6),
				("RIGHTPADDING", (0, 0), (0, -1), 6),
				("LEFTPADDING", (1, 0), (1, -1), 0),
				("RIGHTPADDING", (1, 0), (1, -1), 0),
				("LEFTPADDING", (2, 0), (2, -1), 6),
				("RIGHTPADDING", (2, 0), (2, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 6),
				("BOTTOMPADDING", (0, 0), (-1, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
				("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
				("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#0d6efd")),
			]
		)
	)

	meta_table = Table(
		[
			["PREPARED BY", "ISSUED DATE       |       DUE DATE"],
			[prepared_by, f"{issued}       |       {due}"],
		],
		colWidths=[doc.width * 0.45, doc.width * 0.55],
	)
	meta_table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (0, 0), (-1, 0), "LEFT"),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)

	# Create header table with document type on left and number on right
	header_table = Table(
		[
			["INVOICE", f"No. {invoice.number}"],
		],
		colWidths=[doc.width * 0.5, doc.width * 0.5],
	)
	header_table.setStyle(
		TableStyle(
			[
				("ALIGN", (0, 0), (0, 0), "LEFT"),
				("ALIGN", (1, 0), (1, 0), "RIGHT"),
				("FONTNAME", (0, 0), (-1, -1), base_font_bold),
				("FONTSIZE", (0, 0), (-1, -1), 14),
				("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 0),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)

	elements = [
		header_table,
		Spacer(1, 8),
		to_from_table,
		Spacer(1, 20),
		meta_table,
		Spacer(1, 12),
	]

	items = list(invoice.items.all())
	rows: list[list[object]] = []
	for it in items:
		item_name = "Item"
		try:
			if getattr(it, "product", None) is not None:
				item_name = str(getattr(it.product, "name", None) or it.description or "Item")
			elif getattr(it, "service", None) is not None:
				item_name = str(getattr(it.service, "name", None) or it.description or "Service")
		except Exception:
			item_name = "Item"
		desc = (it.description or "-")
		rows.append(
			[
				Paragraph(str(item_name), item_style),
				Paragraph(str(desc), item_style),
				Paragraph(str(it.quantity), item_style),
				Paragraph(_money(it.unit_price), item_style),
				Paragraph(_money(it.line_total()), item_style),
			]
		)

	if not rows:
		rows = [["(No items)", "-", "-", "-", "-"]]

	data = [["Item", "Description", "Qty", "Unit Price", "Amount"]] + rows
	item_w = 35 * mm
	qty_w = 25 * mm
	unit_w = 27 * mm
	amt_w = 27 * mm
	desc_w = max(40 * mm, float(doc.width) - (item_w + qty_w + unit_w + amt_w))
	item_col_widths = [item_w, desc_w, qty_w, unit_w, amt_w]
	table = Table(data, repeatRows=1, colWidths=item_col_widths)
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (2, 1), (2, -1), "CENTER"),
				("ALIGN", (3, 1), (4, -1), "RIGHT"),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("GRID", (0, 0), (-1, -1), 0.6, colors.black),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	elements.append(table)

	amount_rows = [
		["Sub total", f"{invoice.currency} {_money(invoice.subtotal())}"],
		["VAT 18%", f"{invoice.currency} {_money(invoice.vat_amount())}"],
		["TOTAL", f"{invoice.currency} {_money(invoice.total())}"],
	]
	amount_data = [["Summary", "Amount"]] + amount_rows
	amount_table = Table(
		amount_data,
		colWidths=[item_col_widths[2] + item_col_widths[3], item_col_widths[4]],
	)
	amount_table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("GRID", (0, 0), (-1, -1), 0.6, colors.black),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("ALIGN", (0, 1), (0, -1), "LEFT"),
				("ALIGN", (1, 1), (1, -1), "RIGHT"),
				("FONTNAME", (0, 1), (0, -1), base_font_bold),
				("FONTNAME", (0, -1), (-1, -1), base_font_bold),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	amount_wrap = Table(
		[["", amount_table]],
		colWidths=[item_col_widths[0] + item_col_widths[1], item_col_widths[2] + item_col_widths[3] + item_col_widths[4]],
	)
	amount_wrap.setStyle(
		TableStyle(
			[
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 0),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)
	elements += [Spacer(1, 12), amount_wrap]

	standard_terms_html = _default_notes_html()
	notes_text = (invoice.notes or "").strip()
	if not notes_text:
		notes_text = standard_terms_html
	else:
		# Always include the standard terms even when custom notes exist.
		# Avoid duplicating if someone already pasted them into invoice.notes.
		marker = "system-generated invoice"
		if marker not in notes_text.lower():
			notes_text = notes_text + "<br/><br/>" + standard_terms_html
	# Render notes (either user-provided or defaults) at the bottom above the footer.
	elements += [
		Spacer(1, 12),
		_BottomAlignedFlowables(
			[
				Paragraph("Notes / Terms", styles["pdf_section"]),
				Paragraph(notes_text, note_style),
			]
		),
	]

	doc.build(
		elements,
		onFirstPage=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
		onLaterPages=lambda c, d: _pdf_draw_header_footer(c, d, title=title),
	)
	pdf_bytes = buffer.getvalue()
	buffer.close()
	return pdf_bytes


def _build_receipt_pdf_bytes(payment, *, issued_by: str | None = None) -> bytes:
	from reportlab.lib.units import mm

	buffer = BytesIO()
	title = payment.receipt_number
	doc = SimpleDocTemplate(
		buffer,
		pagesize=A4,
		title=title,
		topMargin=90,
		bottomMargin=72,
		leftMargin=36,
		rightMargin=36,
	)
	styles = getSampleStyleSheet()
	base_font, base_font_bold = _pdf_setup_fonts(styles)
	styles["Title"].textColor = colors.HexColor("#0f172a")
	styles.add(
		ParagraphStyle(
			"pdf_section",
			parent=styles["Heading3"],
			textColor=colors.HexColor("#0f172a"),
			spaceBefore=8,
			spaceAfter=4,
		)
	)
	item_style = ParagraphStyle(
		"pdf_item",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=9.5,
		leading=11,
		textColor=colors.HexColor("#0f172a"),
	)
	note_style = ParagraphStyle(
		"pdf_notes",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=10,
		leading=14,
		textColor=colors.HexColor("#0f172a"),
	)

	def _default_notes_html() -> str:
		payment_methods = (
			"Payment methods accepted: <b>Bank</b>, <b>Mobile Money</b>, and <b>Cash</b>. "
			"Please quote the document number on all payments for easy tracking."
		)
		sep = "<br/><br/>"
		lines = [
			"• Thank you for your business.",
			"• Goods once sold are not returnable.",
			"• This receipt confirms payment received for the invoice listed.",
			"• All payments are subject to verification and reconciliation.",
			"• Refunds are processed within 21 days of payment date.",
			f"• {payment_methods}",
		]
		return sep.join(lines)

	invoice = payment.invoice
	client_name = str(invoice.client)
	client_email = getattr(invoice.client, "email", "") or "-"
	issued_by_name = (issued_by or "").strip()
	if not issued_by_name:
		recorder = getattr(payment, "recorded_by", None)
		issued_by_name = (
			(getattr(recorder, "get_full_name", lambda: "")() if recorder else "")
			or (getattr(recorder, "email", "") if recorder else "")
			or "JAMBAS IMAGING (U) LTD"
		)
	paid_date = timezone.localtime(payment.paid_at).date().isoformat() if payment.paid_at else "-"
	receipt_number = payment.receipt_number or "-"

	blank = ""
	client_obj = getattr(invoice, "client", None)
	address = (getattr(client_obj, "physical_address", "") or "").strip()
	contact_person = (getattr(client_obj, "contact_person", "") or "").strip()
	phone = (getattr(client_obj, "phone", "") or "").strip()
	email = (getattr(client_obj, "email", "") or "").strip()
	if phone and email:
		phone_email_line = f"{phone} / {email}"
	elif phone:
		phone_email_line = phone
	elif email:
		phone_email_line = email
	else:
		phone_email_line = blank


	label_style = ParagraphStyle(
		"pdf_kv_label",
		parent=styles["Normal"],
		fontName=base_font_bold,
		fontSize=9,
		leading=11,
		textColor=colors.HexColor("#0f172a"),
	)
	value_style = ParagraphStyle(
		"pdf_kv_value",
		parent=styles["Normal"],
		fontName=base_font,
		fontSize=9,
		leading=11,
		textColor=colors.HexColor("#0f172a"),
	)

	def _kv_row(label: str, value: str) -> list[object]:
		label_txt = (label or "").strip().upper() + ":"
		return [Paragraph(label_txt, label_style), Paragraph(value or blank, value_style)]

	# Keep TO compact: each parameter on the same line with its value.
	to_kv = Table(
		[
			_kv_row("Client Name", client_name),
			_kv_row("Address", address),
			_kv_row("Contact Person", contact_person),
			_kv_row("Phone", phone),
			_kv_row("Email", email),
		],
		colWidths=[28 * mm, float(doc.width) * 0.5 - 28 * mm],
	)
	to_kv.setStyle(
		TableStyle(
			[
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 1),
				("RIGHTPADDING", (0, 0), (0, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)
	gutter_w = 14 * mm
	to_w = (float(doc.width) - gutter_w) / 2.0
	from_w = (float(doc.width) - gutter_w) / 2.0
	from_kv = Table(
		[
			_kv_row("Company", "JAMBAS IMAGING (U) LTD"),
			_kv_row("Address", "F-26, Nasser Road Mall, Kampala – Uganda"),
			_kv_row("Tel", "+256 200 902 849"),
			_kv_row("Email", "info@jambasimaging.com"),
			_kv_row("Website", "www.jambasimaging.com"),
		],
		colWidths=[28 * mm, from_w - 28 * mm],
	)
	from_kv.setStyle(
		TableStyle(
			[
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 1),
				("RIGHTPADDING", (0, 0), (0, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)

	to_from_table = Table(
		[
			["TO", "", "FROM"],
			[to_kv, "", from_kv],
		],
		# Span full available width so the blue header bar aligns with other tables.
		colWidths=[to_w, gutter_w, from_w],
	)
	# Style the TO/FROM table: blue header, white text; no vertical separators.
	to_from_table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (0, 0), (0, 0), "LEFT"),
				("ALIGN", (2, 0), (2, 0), "LEFT"),
				("LEFTPADDING", (0, 0), (0, -1), 6),
				("RIGHTPADDING", (0, 0), (0, -1), 6),
				("LEFTPADDING", (1, 0), (1, -1), 0),
				("RIGHTPADDING", (1, 0), (1, -1), 0),
				("LEFTPADDING", (2, 0), (2, -1), 6),
				("RIGHTPADDING", (2, 0), (2, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 6),
				("BOTTOMPADDING", (0, 0), (-1, -1), 6),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
				("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
				("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#0d6efd")),
			]
		)
	)

	meta_table = Table(
		[
			["ISSUED BY", "PAID DATE"],
			[issued_by_name, paid_date],
		],
		colWidths=[doc.width * 0.45, doc.width * 0.55],
	)
	meta_table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (0, 0), (-1, 0), "LEFT"),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)

	# Create header table with document type on left and number on right
	header_table = Table(
		[
			["RECEIPT", f"No. {receipt_number}"],
		],
		colWidths=[doc.width * 0.5, doc.width * 0.5],
	)
	header_table.setStyle(
		TableStyle(
			[
				("ALIGN", (0, 0), (0, 0), "LEFT"),
				("ALIGN", (1, 0), (1, 0), "RIGHT"),
				("FONTNAME", (0, 0), (-1, -1), base_font_bold),
				("FONTSIZE", (0, 0), (-1, -1), 14),
				("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 0),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)

	elements = [
		header_table,
		Spacer(1, 8),
		to_from_table,
		Spacer(1, 20),
		meta_table,
		Spacer(1, 12),
	]

	items = list(invoice.items.all())
	rows: list[list[object]] = []
	for it in items:
		item_name = "Item"
		try:
			if getattr(it, "product", None) is not None:
				item_name = str(getattr(it.product, "name", None) or it.description or "Item")
			elif getattr(it, "service", None) is not None:
				item_name = str(getattr(it.service, "name", None) or it.description or "Service")
		except Exception:
			item_name = "Item"
		desc = (it.description or "-")
		rows.append(
			[
				Paragraph(str(item_name), item_style),
				Paragraph(str(desc), item_style),
				Paragraph(str(it.quantity), item_style),
				Paragraph(_money(it.unit_price), item_style),
				Paragraph(_money(it.line_total()), item_style),
			]
		)
	if not rows:
		rows = [[Paragraph("(No items)", item_style), "-", "-", "-", "-"]]

	data = [["Item", "Description", "Qty", "Unit Price", "Amount"]] + rows
	item_w = 35 * mm
	qty_w = 25 * mm
	unit_w = 27 * mm
	amt_w = 27 * mm
	# Make the table span the full available width to keep vertical grid lines
	# perfectly aligned with other right-aligned tables.
	desc_w = max(40 * mm, float(doc.width) - (item_w + qty_w + unit_w + amt_w))
	item_col_widths = [item_w, desc_w, qty_w, unit_w, amt_w]
	table = Table(data, repeatRows=1, colWidths=item_col_widths)
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (2, 1), (2, -1), "CENTER"),
				("ALIGN", (3, 1), (4, -1), "RIGHT"),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("GRID", (0, 0), (-1, -1), 0.6, colors.black),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	elements.append(table)

	# For receipt, summary includes payment details
	amount_rows: list[list[str]] = [
		["Invoice Total", f"{invoice.currency} {_money(invoice.total())}"],
		["Payment Amount", f"{invoice.currency} {_money(payment.amount)}"],
		["Total Paid", f"{invoice.currency} {_money(invoice.amount_paid())}"],
		["Outstanding", f"{invoice.currency} {_money(invoice.outstanding_balance())}"],
	]

	amount_data = [["Summary", "Amount"]] + amount_rows
	amount_table = Table(
		amount_data,
		colWidths=[item_col_widths[2] + item_col_widths[3], item_col_widths[4]],
	)
	amount_table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), base_font_bold),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("GRID", (0, 0), (-1, -1), 0.6, colors.black),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("ALIGN", (0, 1), (0, -1), "LEFT"),
				("ALIGN", (1, 1), (1, -1), "RIGHT"),
				("FONTNAME", (0, 1), (0, -1), base_font_bold),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	amount_wrap = Table(
		[["", amount_table]],
		colWidths=[item_col_widths[0] + item_col_widths[1], item_col_widths[2] + item_col_widths[3] + item_col_widths[4]],
	)
	amount_wrap.setStyle(
		TableStyle(
			[
				("LEFTPADDING", (0, 0), (-1, -1), 0),
				("RIGHTPADDING", (0, 0), (-1, -1), 0),
				("TOPPADDING", (0, 0), (-1, -1), 0),
				("BOTTOMPADDING", (0, 0), (-1, -1), 0),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
			]
		)
	)
	elements += [Spacer(1, 12), amount_wrap]

	notes_text = (payment.notes or "").strip()
	if not notes_text:
		notes_text = _default_notes_html()
	else:
		extra_terms: list[str] = []
		if "Thank you" not in notes_text:
			extra_terms.append("• Thank you for your business.")
		if "not returnable" not in notes_text.lower():
			extra_terms.append("• Goods once sold are not returnable.")
		if extra_terms:
			notes_text = notes_text + "<br/><br/>" + "<br/><br/>".join(extra_terms)
	# Render notes (either user-provided or defaults) at the bottom above the footer.
	elements += [
		Spacer(1, 12),
		_BottomAlignedFlowables(
			[
				Paragraph("Notes / Terms", styles["pdf_section"]),
				Paragraph(notes_text, note_style),
			]
		),
	]

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
	from invoices.models import PaymentRefund
	from documents.models import Document

	invoice = (
		Invoice.objects.select_related("client", "branch")
		.prefetch_related("items", "payments")
		.get(pk=invoice_id)
	)
	# Ensure invoice status stays consistent with payments, including
	# rounding-tolerant outstanding balance.
	try:
		invoice.refresh_status_from_payments(save=True)
	except Exception:
		pass

	invoice_docs = Document.objects.filter(related_invoice=invoice).order_by("-uploaded_at", "-version")
	receipt_docs = Document.objects.filter(
		related_payment_id__in=list(invoice.payments.values_list("id", flat=True))
	).order_by("-uploaded_at", "-version")
	receipt_doc_by_payment_id = {d.related_payment_id: d for d in receipt_docs if d.related_payment_id}
	for p in invoice.payments.all():
		p.archived_receipt_doc = receipt_doc_by_payment_id.get(p.id)

	refunds = PaymentRefund.objects.select_related("payment", "refunded_by").filter(invoice_id=invoice.id)

	payment_form = PaymentForm(invoice=invoice)
	signature_form = InvoiceSignatureForm(initial={"name": invoice.signed_by_name or ""})
	if not (invoice.signed_by_name or "").strip():
		shift_signed = (request.session.get("signed_by_name") or "").strip()
		if shift_signed:
			signature_form = InvoiceSignatureForm(initial={"name": shift_signed})
	context = {
		"invoice": invoice,
		"items": invoice.items.all(),
		"payments": invoice.payments.all(),
		"refunds": refunds,
		"is_admin": _is_admin(request.user),
		"invoice_documents": invoice_docs[:20],
		"payment_form": payment_form,
		"signature_form": signature_form,
		"totals": {
			"subtotal": invoice.subtotal(),
			"vat": invoice.vat_amount(),
			"total": invoice.total(),
			"paid": invoice.amount_paid(),
			"refunded": invoice.amount_refunded(),
			"balance": invoice.outstanding_balance(),
		},
	}
	return render(request, "modules/invoice_detail.html", context)


@login_required
def refund_payment(request, invoice_id: int, payment_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard

	from invoices.models import Payment
	from invoices.forms import PaymentRefundForm

	payment = Payment.objects.select_related("invoice", "invoice__client").get(pk=payment_id, invoice_id=invoice_id)
	if not getattr(payment, "is_refund_window_open", True):
		deadline_local = timezone.localtime(payment.refund_deadline)
		messages.error(
			request,
			f"Refund window expired. Refunds are allowed within 21 days of payment date (deadline: {deadline_local:%Y-%m-%d %H:%M}).",
		)
		return redirect("invoice_detail", invoice_id=invoice_id)

	if request.method == "POST":
		form = PaymentRefundForm(request.POST, payment=payment)
		if form.is_valid():
			refund = form.save(commit=False)
			refund.refunded_by = request.user
			refund.save()
			messages.success(request, "Refund recorded.")
			return redirect("invoice_detail", invoice_id=invoice_id)
	else:
		form = PaymentRefundForm(payment=payment)

	return render(
		request,
		"modules/refund_payment.html",
		{
			"invoice": payment.invoice,
			"payment": payment,
			"form": form,
		},
	)


@login_required
def delete_invoice_payment(request, invoice_id: int, payment_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("invoice_detail", invoice_id=invoice_id)

	from invoices.models import Invoice, Payment

	invoice = Invoice.objects.get(pk=invoice_id)
	Payment.objects.filter(pk=payment_id, invoice_id=invoice_id).delete()
	invoice.refresh_status_from_payments(save=True)
	messages.success(request, "Payment deleted.")
	return redirect("invoice_detail", invoice_id=invoice_id)


@login_required
def delete_payment_refund(request, invoice_id: int, refund_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("invoice_detail", invoice_id=invoice_id)

	from invoices.models import Invoice, PaymentRefund

	invoice = Invoice.objects.get(pk=invoice_id)
	PaymentRefund.objects.filter(pk=refund_id, invoice_id=invoice_id).delete()
	invoice.refresh_status_from_payments(save=True)
	messages.success(request, "Refund deleted.")
	return redirect("invoice_detail", invoice_id=invoice_id)


@login_required
def sign_invoice(request, invoice_id: int):
	from invoices.models import Invoice
	from invoices.forms import InvoiceSignatureForm

	invoice = Invoice.objects.get(pk=invoice_id)
	if request.method != "POST":
		return redirect("invoice_detail", invoice_id=invoice_id)

	form = InvoiceSignatureForm(request.POST)
	if form.is_valid():
		shift_name = (request.session.get("signed_by_name") or "").strip()
		name = shift_name or (form.cleaned_data.get("name") or "").strip()
		if not name:
			messages.error(request, "Please set Approved by in Shift Identity.")
			return redirect("invoice_detail", invoice_id=invoice_id)
		invoice.signed_by_name = name
		invoice.signed_at = timezone.now() if name else None
		invoice.save(update_fields=["signed_by_name", "signed_at"])
		try:
			invoice.deduct_stock_if_needed()
		except Exception:
			pass
		messages.success(request, "Invoice approved.")
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
@xframe_options_sameorigin
def payment_receipt_pdf(request, invoice_id: int, payment_id: int):
	from invoices.models import Payment

	payment = Payment.objects.select_related("invoice", "invoice__client").get(pk=payment_id, invoice_id=invoice_id)
	shift_issued = (request.session.get("issued_by_name") or request.session.get("prepared_by_name") or "").strip() or None
	pdf_bytes = _build_receipt_pdf_bytes(payment, issued_by=shift_issued)
	client_label = str(payment.invoice.client).replace(" ", "_")[:40] if payment.invoice and payment.invoice.client else "Client"
	reference = payment.receipt_number or str(payment.pk)
	filename = f"Receipt_{client_label}_{reference}.pdf"
	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	extra_inline = _get_str(request, "inline")
	if extra_inline in {"1", "true", "yes", "on"}:
		response["Content-Disposition"] = f'inline; filename="{filename}"'
	else:
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

	shift_issued = (request.session.get("issued_by_name") or request.session.get("prepared_by_name") or "").strip() or None
	pdf_bytes = _build_receipt_pdf_bytes(payment, issued_by=shift_issued)
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
	client_label = str(payment.invoice.client).replace(" ", "_")[:40] if payment.invoice and payment.invoice.client else "Client"
	reference = payment.receipt_number or str(payment.pk)
	filename = f"Receipt_{client_label}_{reference}.pdf"
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
@xframe_options_sameorigin
def invoice_pdf(request, invoice_id: int):
	from invoices.models import Invoice

	invoice = Invoice.objects.select_related("client").prefetch_related("items", "payments").get(pk=invoice_id)
	pdf_bytes = _build_invoice_pdf_bytes(invoice)
	client_label = str(invoice.client).replace(" ", "_")[:40] or "Client"
	filename = f"Invoice_{client_label}_{invoice.number}.pdf"
	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	extra_inline = _get_str(request, "inline")
	if extra_inline in {"1", "true", "yes", "on"}:
		response["Content-Disposition"] = f'inline; filename="{filename}"'
	else:
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
	client_label = str(invoice.client).replace(" ", "_")[:40] or "Client"
	filename = f"Invoice_{client_label}_{invoice.number}.pdf"
	msg.attach(filename=filename, content=pdf_bytes, mimetype="application/pdf")
	try:
		msg.send(fail_silently=False)
		# Mark as issued when successfully sent.
		if invoice.status not in {Invoice.Status.PAID, Invoice.Status.CANCELLED}:
			invoice.status = Invoice.Status.ISSUED
			if not invoice.issued_at:
				invoice.issued_at = timezone.localdate()
			invoice.save(update_fields=["status", "issued_at"])
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
@xframe_options_sameorigin
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

	extra_inline = _get_str(request, "inline")
	return _pdf_response(
		title="Invoices",
		header=["Number", "Client", "Status", "Issued", "Due"],
		rows=rows,
		filename="invoices.pdf",
		inline=extra_inline in {"1", "true", "yes", "on"},
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
		"is_admin": _is_admin(request.user),
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


@login_required
def edit_inventory(request, product_id: int):
	from inventory.forms import ProductForm
	from inventory.models import Product

	product = get_object_or_404(Product, pk=product_id)
	if request.method == "POST":
		form = ProductForm(request.POST, instance=product)
		if form.is_valid():
			form.save()
			messages.success(request, "Product updated.")
			return redirect("inventory")
	else:
		form = ProductForm(instance=product)

	return render(request, "modules/edit_inventory.html", {"form": form, "product": product})


@login_required
def delete_inventory(request, product_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("inventory")

	from django.db.models.deletion import ProtectedError
	from inventory.models import Product

	product = get_object_or_404(Product, pk=product_id)
	try:
		product.delete()
		messages.success(request, "Product deleted.")
	except ProtectedError:
		# Product is referenced by invoices/stock movements. Keep history intact.
		Product.objects.filter(pk=product.pk).update(is_active=False)
		messages.warning(request, "Product is in use and cannot be deleted; it was deactivated instead.")
	return redirect("inventory")


@login_required
def stock_movements_view(request):
	from inventory.models import StockMovement
	from django.db.models import Q

	q = _get_str(request, "q")
	mtype = _get_str(request, "type")

	qs = StockMovement.objects.select_related("product").all().order_by("-occurred_at", "-id")
	if q:
		qs = qs.filter(Q(product__sku__icontains=q) | Q(product__name__icontains=q) | Q(reference__icontains=q))
	if mtype in {"in", "out"}:
		qs = qs.filter(movement_type=mtype)

	return render(
		request,
		"modules/stock_movements.html",
		{
			"movements": qs[:200],
			"filters": {"q": q, "type": mtype},
		},
	)


@login_required
def adjust_stock(request, product_id: int):
	from inventory.forms import StockMovementAdjustForm
	from inventory.models import Product

	product = get_object_or_404(Product, pk=product_id)
	if request.method == "POST":
		form = StockMovementAdjustForm(request.POST, product=product)
		if form.is_valid():
			form.save()
			messages.success(request, "Stock updated.")
			return redirect("inventory")
	else:
		initial = {}
		movement_type = _get_str(request, "type")
		if movement_type in {"in", "out"}:
			initial["movement_type"] = movement_type
		form = StockMovementAdjustForm(product=product, initial=initial)

	return render(request, "modules/adjust_stock.html", {"product": product, "form": form})


def suppliers_view(request):
	"""Suppliers register (list + filters)."""
	from inventory.models import Supplier

	q = (request.GET.get("q") or "").strip()
	is_active = (request.GET.get("is_active") or "").strip()
	product_name = (request.GET.get("product") or "").strip()
	min_price_raw = (request.GET.get("min_price") or "").strip()
	max_price_raw = (request.GET.get("max_price") or "").strip()
	min_price = None
	max_price = None
	try:
		if min_price_raw:
			min_price = Decimal(min_price_raw)
	except Exception:
		min_price = None
	try:
		if max_price_raw:
			max_price = Decimal(max_price_raw)
	except Exception:
		max_price = None

	qs = Supplier.objects.all().order_by("name")
	if q:
		qs = qs.filter(name__icontains=q)
	if is_active in {"0", "1"}:
		qs = qs.filter(is_active=(is_active == "1"))
	if product_name:
		qs = qs.filter(
			models.Q(product_prices__item_name__icontains=product_name)
			| models.Q(product_prices__product__name__icontains=product_name)
		)
	if min_price is not None:
		qs = qs.filter(product_prices__unit_price__gte=min_price)
	if max_price is not None:
		qs = qs.filter(product_prices__unit_price__lte=max_price)
	qs = qs.distinct().prefetch_related("product_prices__product")

	# Attach a small sample of what each supplier supplies and at which rate.
	suppliers = list(qs)
	for s in suppliers:
		prices = [p for p in s.product_prices.all() if p.is_active][:3]
		setattr(s, "sample_prices", prices)

	context = {
		"suppliers": suppliers,
		"filters": {
			"q": q,
			"is_active": is_active,
			"product": product_name,
			"min_price": min_price_raw,
			"max_price": max_price_raw,
		},
	}
	return render(request, "modules/suppliers.html", context)


def add_supplier(request):
	from inventory.forms import SupplierForm

	if request.method == "POST":
		form = SupplierForm(request.POST)
		if form.is_valid():
			supplier = form.save()
			# After creating a supplier, go straight to its page where
			# you can capture what they supply and at which rate.
			return redirect("supplier_detail", supplier_id=supplier.id)
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

	return render(
		request,
		"modules/edit_supplier.html",
		{"form": form, "supplier": supplier},
	)


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


@login_required
def edit_supplier_price(request, price_id: int):
	"""Edit a single supplier supply/price line.

	Keeps the supplier fixed but lets you adjust what they supply,
	unit, price, minimum order, lead time, etc.
	"""
	from inventory.forms import SupplierProductPriceForm
	from inventory.models import SupplierProductPrice

	price = get_object_or_404(SupplierProductPrice.objects.select_related("supplier"), pk=price_id)
	supplier = price.supplier
	if request.method == "POST":
		form = SupplierProductPriceForm(request.POST, instance=price)
		# Ensure supplier does not accidentally change via POST.
		if "supplier" in form.fields:
			form.fields["supplier"].disabled = True
		if form.is_valid():
			obj = form.save(commit=False)
			obj.supplier = supplier
			obj.save()
			messages.success(request, "Supply/price updated.")
			return redirect("supplier_detail", supplier_id=supplier.id)
	else:
		form = SupplierProductPriceForm(instance=price, initial={"supplier": supplier})
		if "supplier" in form.fields:
			form.fields["supplier"].disabled = True

	return render(
		request,
		"modules/edit_supplier_price.html",
		{"form": form, "supplier": supplier, "price": price},
	)


@login_required
def delete_supplier_price(request, price_id: int):
	from inventory.models import SupplierProductPrice

	price = get_object_or_404(SupplierProductPrice, pk=price_id)
	supplier_id = price.supplier_id
	if request.method == "POST":
		price.delete()
		messages.success(request, "Supply/price deleted.")
	return redirect("supplier_detail", supplier_id=supplier_id)


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
def services_view(request):
	"""Services catalog (list + filters)."""
	from core.models import Branch
	from services.models import Service, ServiceCategory
	from django.db.models import Q

	q = _get_str(request, "q")
	branch_id = _get_int(request, "branch")
	category_id = _get_int(request, "category")
	is_active = _get_str(request, "is_active")

	qs = Service.objects.select_related("branch", "category").all().order_by("name")
	if q:
		qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
	if branch_id is not None:
		qs = qs.filter(branch_id=branch_id)
	if category_id is not None:
		qs = qs.filter(category_id=category_id)
	if is_active in {"0", "1"}:
		qs = qs.filter(is_active=(is_active == "1"))

	context = {
		"services": qs[:100],
		"services_total": qs.count(),
		"services_active": qs.filter(is_active=True).count(),
		"is_admin": _is_admin(request.user),
		"branches": Branch.objects.filter(is_active=True),
		"categories": ServiceCategory.objects.all().order_by("name"),
		"filters": {
			"q": q,
			"branch": _get_str(request, "branch"),
			"category": _get_str(request, "category"),
			"is_active": is_active,
		},
		"qs": _current_querystring(request),
	}
	return render(request, "modules/services.html", context)


@login_required
def add_service(request):
	from services.forms import ServiceForm

	if request.method == "POST":
		form = ServiceForm(request.POST)
		if form.is_valid():
			form.save()
			messages.success(request, "Service created.")
			return redirect("services")
	else:
		form = ServiceForm()

	return render(request, "modules/add_service.html", {"form": form})


@login_required
def edit_service(request, service_id: int):
	from services.forms import ServiceForm
	from services.models import Service

	service = get_object_or_404(Service, pk=service_id)
	if request.method == "POST":
		form = ServiceForm(request.POST, instance=service)
		if form.is_valid():
			form.save()
			messages.success(request, "Service updated.")
			return redirect("services")
	else:
		form = ServiceForm(instance=service)

	return render(request, "modules/edit_service.html", {"form": form, "service": service})


@login_required
def delete_service(request, service_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("services")

	from django.db.models.deletion import ProtectedError
	from services.models import Service

	service = get_object_or_404(Service, pk=service_id)
	try:
		service.delete()
		messages.success(request, "Service deleted.")
	except ProtectedError:
		Service.objects.filter(pk=service.pk).update(is_active=False)
		messages.warning(request, "Service is in use and cannot be deleted; it was deactivated instead.")
	return redirect("services")


@login_required
def service_categories_view(request):
	from services.models import ServiceCategory

	categories = ServiceCategory.objects.all().order_by("name")
	return render(
		request,
		"modules/service_categories.html",
		{
			"categories": categories,
			"is_admin": _is_admin(request.user),
		},
	)


@login_required
def add_service_category(request):
	from services.forms import ServiceCategoryForm

	if request.method == "POST":
		form = ServiceCategoryForm(request.POST)
		if form.is_valid():
			form.save()
			messages.success(request, "Category created.")
			return redirect("service_categories")
	else:
		form = ServiceCategoryForm()

	return render(request, "modules/add_service_category.html", {"form": form})


@login_required
def edit_service_category(request, category_id: int):
	from services.forms import ServiceCategoryForm
	from services.models import ServiceCategory

	category = get_object_or_404(ServiceCategory, pk=category_id)
	if request.method == "POST":
		form = ServiceCategoryForm(request.POST, instance=category)
		if form.is_valid():
			form.save()
			messages.success(request, "Category updated.")
			return redirect("service_categories")
	else:
		form = ServiceCategoryForm(instance=category)

	return render(request, "modules/edit_service_category.html", {"form": form, "category": category})


@login_required
def delete_service_category(request, category_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("service_categories")

	from django.db.models.deletion import ProtectedError
	from services.models import ServiceCategory

	category = get_object_or_404(ServiceCategory, pk=category_id)
	try:
		category.delete()
		messages.success(request, "Category deleted.")
	except ProtectedError:
		messages.warning(request, "Category is in use and cannot be deleted.")
	return redirect("service_categories")


@login_required
def inventory_categories_view(request):
	from inventory.models import ProductCategory

	categories = ProductCategory.objects.all().order_by("name")
	return render(
		request,
		"modules/inventory_categories.html",
		{
			"categories": categories,
			"is_admin": _is_admin(request.user),
		},
	)


@login_required
def add_inventory_category(request):
	from inventory.forms import ProductCategoryForm

	if request.method == "POST":
		form = ProductCategoryForm(request.POST)
		if form.is_valid():
			form.save()
			messages.success(request, "Category created.")
			return redirect("inventory_categories")
	else:
		form = ProductCategoryForm()

	return render(request, "modules/add_inventory_category.html", {"form": form})


@login_required
def edit_inventory_category(request, category_id: int):
	from inventory.forms import ProductCategoryForm
	from inventory.models import ProductCategory

	category = get_object_or_404(ProductCategory, pk=category_id)
	if request.method == "POST":
		form = ProductCategoryForm(request.POST, instance=category)
		if form.is_valid():
			form.save()
			messages.success(request, "Category updated.")
			return redirect("inventory_categories")
	else:
		form = ProductCategoryForm(instance=category)

	return render(request, "modules/edit_inventory_category.html", {"form": form, "category": category})


@login_required
def delete_inventory_category(request, category_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard
	if request.method != "POST":
		return redirect("inventory_categories")

	from django.db.models.deletion import ProtectedError
	from inventory.models import ProductCategory

	category = get_object_or_404(ProductCategory, pk=category_id)
	try:
		category.delete()
		messages.success(request, "Category deleted.")
	except ProtectedError:
		messages.warning(request, "Category is in use and cannot be deleted.")
	return redirect("inventory_categories")


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
	writer.writerow(["SKU", "Name", "Category", "Supplier", "Unit Price", "Stock", "Reorder Level"]) 
	qs = Product.objects.select_related("category", "supplier", "branch").all().order_by("name")
	qs = _filter_inventory(request, qs)
	for p in qs:
		writer.writerow([
			p.sku,
			p.name,
			str(p.category),
			str(p.supplier) if p.supplier else "",
			_money(p.unit_price),
			str(p.stock_quantity),
			str(p.low_stock_threshold),
		])
	return response


@login_required
@xframe_options_sameorigin
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

	extra_inline = _get_str(request, "inline")
	return _pdf_response(
		title="Inventory",
		header=["SKU", "Name", "Category", "Stock", "Status"],
		rows=rows,
		filename="inventory.pdf",
		inline=extra_inline in {"1", "true", "yes", "on"},
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
			_money(e.amount),
			e.reference,
		])
	return response


@login_required
@xframe_options_sameorigin
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
			_money(e.amount),
		])

	extra_inline = _get_str(request, "inline")
	return _pdf_response(
		title="Expenses",
		header=["Date", "Branch", "Category", "Description", "Amount"],
		rows=rows,
		filename="expenses.pdf",
		inline=extra_inline in {"1", "true", "yes", "on"},
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
@xframe_options_sameorigin
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

	extra_inline = _get_str(request, "inline")
	return _pdf_response(
		title="Appointments",
		header=["Scheduled", "Client", "Type", "Status", "Assigned"],
		rows=rows,
		filename="appointments.pdf",
		inline=extra_inline in {"1", "true", "yes", "on"},
	)


@login_required
def reports_view(request):
	"""Reports frontend page (UI only)."""
	guard = _require_admin(request)
	if guard is not None:
		return guard
	from appointments.models import Appointment
	from clients.models import Client
	from core.models import Branch
	from django.core.paginator import Paginator
	from django.db.models import Sum
	from inventory.models import Product
	from invoices.models import Invoice
	from invoices.models import Payment, PaymentRefund
	from expenses.models import Expense
	from reports.models import ProfitRecord

	now = timezone.now()

	# Optional report filters
	branch_id = _get_int(request, "branch")
	from_date = _get_date(request, "from")
	to_date = _get_date(request, "to")

	clients_qs = Client.objects.all()
	invoices_qs = Invoice.objects.all()
	payments_qs = Payment.objects.select_related("invoice").all()
	refunds_qs = PaymentRefund.objects.select_related("invoice").all()
	expenses_qs = Expense.objects.all()
	appointments_qs = Appointment.objects.all()
	products_qs = Product.objects.all()
	if branch_id is not None:
		clients_qs = clients_qs.filter(branch_id=branch_id)
		invoices_qs = invoices_qs.filter(branch_id=branch_id)
		payments_qs = payments_qs.filter(invoice__branch_id=branch_id)
		refunds_qs = refunds_qs.filter(invoice__branch_id=branch_id)
		expenses_qs = expenses_qs.filter(branch_id=branch_id)
		appointments_qs = appointments_qs.filter(branch_id=branch_id)
		products_qs = products_qs.filter(branch_id=branch_id)
	if from_date:
		invoices_qs = invoices_qs.filter(created_at__date__gte=from_date)
		clients_qs = clients_qs.filter(created_at__date__gte=from_date)
		payments_qs = payments_qs.filter(paid_at__date__gte=from_date)
		refunds_qs = refunds_qs.filter(refunded_at__date__gte=from_date)
		expenses_qs = expenses_qs.filter(expense_date__gte=from_date)
		appointments_qs = appointments_qs.filter(created_at__date__gte=from_date)
		products_qs = products_qs.filter(created_at__date__gte=from_date)
	if to_date:
		invoices_qs = invoices_qs.filter(created_at__date__lte=to_date)
		clients_qs = clients_qs.filter(created_at__date__lte=to_date)
		payments_qs = payments_qs.filter(paid_at__date__lte=to_date)
		refunds_qs = refunds_qs.filter(refunded_at__date__lte=to_date)
		expenses_qs = expenses_qs.filter(expense_date__lte=to_date)
		appointments_qs = appointments_qs.filter(created_at__date__lte=to_date)
		products_qs = products_qs.filter(created_at__date__lte=to_date)

	clients_total = clients_qs.count()
	clients_active = clients_qs.filter(status=Client.Status.ACTIVE).count()
	invoices_total = invoices_qs.count()
	invoices_paid = invoices_qs.filter(status=Invoice.Status.PAID).count()
	show_income = _can_view_income(request.user)
	payments_total = payments_qs.aggregate(total=Sum("amount")).get("total") or 0
	refunds_total = refunds_qs.aggregate(total=Sum("amount")).get("total") or 0
	revenue_total = (payments_total - refunds_total) if show_income else None
	payments_total = payments_total if show_income else None

	# Profit is recorded independently when invoices become PAID.
	service_cost_total = None
	service_profit_total = None
	product_cost_total = None
	product_profit_total = None
	if show_income:
		records = ProfitRecord.objects.select_related("invoice").all()
		if branch_id is not None:
			records = records.filter(invoice__branch_id=branch_id)
		if from_date:
			records = records.filter(invoice__created_at__date__gte=from_date)
		if to_date:
			records = records.filter(invoice__created_at__date__lte=to_date)
		aggs = records.aggregate(
			service_cost=Sum("service_cost_total"),
			service_profit=Sum("service_profit_total"),
			product_cost=Sum("product_cost_total"),
			product_profit=Sum("product_profit_total"),
		)
		service_cost_total = aggs.get("service_cost") or Decimal("0.00")
		service_profit_total = aggs.get("service_profit") or Decimal("0.00")
		product_cost_total = aggs.get("product_cost") or Decimal("0.00")
		product_profit_total = aggs.get("product_profit") or Decimal("0.00")
	expenses_total = expenses_qs.aggregate(total=Sum("amount")).get("total") or 0
	invoiced_total = sum((inv.total() for inv in invoices_qs), Decimal("0.00")) if show_income else None
	outstanding_total = sum((inv.outstanding_balance() for inv in invoices_qs), Decimal("0.00")) if show_income else None
	net_profit = (
		revenue_total
		- expenses_total
		- (service_cost_total or Decimal("0.00"))
		- (product_cost_total or Decimal("0.00"))
	) if show_income else None
	appointments_upcoming = appointments_qs.filter(scheduled_for__gte=now).count()
	products_total = products_qs.count()
	products_low_stock = products_qs.filter(stock_quantity__lte=F("low_stock_threshold")).count()

	context = {
		"kpis": {
			"clients_total": clients_total,
			"clients_active": clients_active,
			"invoices_total": invoices_total,
			"invoices_paid": invoices_paid,
			"payments_total": payments_total,
			"revenue_total": revenue_total,
			"refunds_total": refunds_total if show_income else None,
			"invoiced_total": invoiced_total,
			"outstanding_total": outstanding_total,
			"expenses_total": expenses_total,
			"net_profit": net_profit,
			"service_cost_total": service_cost_total,
			"service_profit_total": service_profit_total,
			"product_cost_total": product_cost_total,
			"product_profit_total": product_profit_total,
			"products_total": products_total,
			"products_low_stock": products_low_stock,
			"appointments_upcoming": appointments_upcoming,
		},
		"recent_invoice_rows": [],
		"recent_invoice_page": None,
		"qs_no_inv_page": "",
		"show_income": show_income,
		"branches": Branch.objects.filter(is_active=True),
		"filters": {
			"branch": _get_str(request, "branch"),
			"from": _get_str(request, "from"),
			"to": _get_str(request, "to"),
		},
		"qs": "",
	}

	# Export links and pagination should not carry table page params.
	context["qs"] = "?" + urlencode(
		{k: v for k, v in request.GET.items() if v not in (None, "") and k not in {"inv_page"}}
	) if request.GET else ""
	context["qs_no_inv_page"] = context["qs"]

	if show_income:
		inv_page = _get_int(request, "inv_page") or 1
		recent_invoices_qs = (
			invoices_qs.select_related("client", "branch")
			.prefetch_related("payments", "refunds", "items")
			.order_by("-created_at")
		)
		paginator = Paginator(recent_invoices_qs, 25)
		page_obj = paginator.get_page(inv_page)
		recent_rows: list[dict] = []
		for inv in page_obj.object_list:
			total = inv.total()
			paid = inv.amount_paid()
			outstanding = inv.outstanding_balance()
			recent_rows.append({
				"invoice": inv,
				"total": total,
				"paid": paid,
				"outstanding": outstanding,
				"is_partial": paid > Decimal("0.00") and outstanding > Decimal("0.00"),
			})
		context["recent_invoice_page"] = page_obj
		context["recent_invoice_rows"] = recent_rows
	return render(request, "modules/reports.html", context)


@login_required
def export_reports_csv(request):
	"""Download report KPI summary as CSV (respects report filters)."""
	guard = _require_admin(request)
	if guard is not None:
		return guard
	# Reuse reports_view calculations by duplicating the same filtered QS logic.
	from appointments.models import Appointment
	from clients.models import Client
	from django.db.models import Sum
	from inventory.models import Product
	from invoices.models import Invoice
	from invoices.models import Payment, PaymentRefund
	from expenses.models import Expense
	from reports.models import ProfitRecord

	now = timezone.now()
	branch_id = _get_int(request, "branch")
	from_date = _get_date(request, "from")
	to_date = _get_date(request, "to")

	clients_qs = Client.objects.all()
	invoices_qs = Invoice.objects.all()
	payments_qs = Payment.objects.select_related("invoice").all()
	refunds_qs = PaymentRefund.objects.select_related("invoice").all()
	expenses_qs = Expense.objects.all()
	appointments_qs = Appointment.objects.all()
	products_qs = Product.objects.all()
	if branch_id is not None:
		clients_qs = clients_qs.filter(branch_id=branch_id)
		invoices_qs = invoices_qs.filter(branch_id=branch_id)
		payments_qs = payments_qs.filter(invoice__branch_id=branch_id)
		refunds_qs = refunds_qs.filter(invoice__branch_id=branch_id)
		expenses_qs = expenses_qs.filter(branch_id=branch_id)
		appointments_qs = appointments_qs.filter(branch_id=branch_id)
		products_qs = products_qs.filter(branch_id=branch_id)
	if from_date:
		invoices_qs = invoices_qs.filter(created_at__date__gte=from_date)
		clients_qs = clients_qs.filter(created_at__date__gte=from_date)
		payments_qs = payments_qs.filter(paid_at__date__gte=from_date)
		refunds_qs = refunds_qs.filter(refunded_at__date__gte=from_date)
		expenses_qs = expenses_qs.filter(expense_date__gte=from_date)
		appointments_qs = appointments_qs.filter(created_at__date__gte=from_date)
		products_qs = products_qs.filter(created_at__date__gte=from_date)
	if to_date:
		invoices_qs = invoices_qs.filter(created_at__date__lte=to_date)
		clients_qs = clients_qs.filter(created_at__date__lte=to_date)
		payments_qs = payments_qs.filter(paid_at__date__lte=to_date)
		refunds_qs = refunds_qs.filter(refunded_at__date__lte=to_date)
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
	payments_total = payments_qs.aggregate(total=Sum("amount")).get("total") or 0
	refunds_total = refunds_qs.aggregate(total=Sum("amount")).get("total") or 0
	revenue_total = (payments_total - refunds_total) if show_income else None
	service_cost_total = None
	service_profit_total = None
	product_cost_total = None
	product_profit_total = None
	if show_income:
		records = ProfitRecord.objects.select_related("invoice").all()
		if branch_id is not None:
			records = records.filter(invoice__branch_id=branch_id)
		if from_date:
			records = records.filter(invoice__created_at__date__gte=from_date)
		if to_date:
			records = records.filter(invoice__created_at__date__lte=to_date)
		aggs = records.aggregate(
			service_cost=Sum("service_cost_total"),
			service_profit=Sum("service_profit_total"),
			product_cost=Sum("product_cost_total"),
			product_profit=Sum("product_profit_total"),
		)
		service_cost_total = aggs.get("service_cost") or Decimal("0.00")
		service_profit_total = aggs.get("service_profit") or Decimal("0.00")
		product_cost_total = aggs.get("product_cost") or Decimal("0.00")
		product_profit_total = aggs.get("product_profit") or Decimal("0.00")
	expenses_total = expenses_qs.aggregate(total=Sum("amount")).get("total") or 0
	invoiced_total = sum((inv.total() for inv in invoices_qs), Decimal("0.00")) if show_income else None
	outstanding_total = sum((inv.outstanding_balance() for inv in invoices_qs), Decimal("0.00")) if show_income else None
	if show_income:
		writer.writerow(["Total Invoiced", _money(invoiced_total)])
		writer.writerow(["Revenue (Net)", _money(revenue_total)])
		writer.writerow(["Refunds", _money(refunds_total)])
		writer.writerow(["Product Cost (COGS)", _money(product_cost_total)])
		writer.writerow(["Product Gross Profit", _money(product_profit_total)])
		writer.writerow(["Service Charges (COGS)", _money(service_cost_total)])
		writer.writerow(["Service Gross Profit", _money(service_profit_total)])
	writer.writerow(["Expenses", _money(expenses_total)])
	if show_income:
		writer.writerow(["Outstanding Balances", _money(outstanding_total)])
		writer.writerow(["Net Profit", _money(revenue_total - expenses_total - service_cost_total - product_cost_total)])
	writer.writerow(["Appointments Upcoming", appointments_qs.filter(scheduled_for__gte=now).count()])
	writer.writerow(["Products Total", products_qs.count()])
	writer.writerow(["Products Low Stock", products_qs.filter(stock_quantity__lte=F("low_stock_threshold")).count()])
	return response


@login_required
@xframe_options_sameorigin
def export_reports_pdf(request):
	"""Download report KPI summary as PDF (respects report filters)."""
	guard = _require_admin(request)
	if guard is not None:
		return guard
	from appointments.models import Appointment
	from clients.models import Client
	from django.db.models import Sum
	from inventory.models import Product
	from invoices.models import Invoice
	from invoices.models import Payment, PaymentRefund
	from expenses.models import Expense
	from reports.models import ProfitRecord

	now = timezone.now()
	branch_id = _get_int(request, "branch")
	from_date = _get_date(request, "from")
	to_date = _get_date(request, "to")

	clients_qs = Client.objects.all()
	invoices_qs = Invoice.objects.all()
	payments_qs = Payment.objects.select_related("invoice").all()
	refunds_qs = PaymentRefund.objects.select_related("invoice").all()
	expenses_qs = Expense.objects.all()
	appointments_qs = Appointment.objects.all()
	products_qs = Product.objects.all()
	if branch_id is not None:
		clients_qs = clients_qs.filter(branch_id=branch_id)
		invoices_qs = invoices_qs.filter(branch_id=branch_id)
		payments_qs = payments_qs.filter(invoice__branch_id=branch_id)
		refunds_qs = refunds_qs.filter(invoice__branch_id=branch_id)
		expenses_qs = expenses_qs.filter(branch_id=branch_id)
		appointments_qs = appointments_qs.filter(branch_id=branch_id)
		products_qs = products_qs.filter(branch_id=branch_id)
	if from_date:
		invoices_qs = invoices_qs.filter(created_at__date__gte=from_date)
		clients_qs = clients_qs.filter(created_at__date__gte=from_date)
		payments_qs = payments_qs.filter(paid_at__date__gte=from_date)
		refunds_qs = refunds_qs.filter(refunded_at__date__gte=from_date)
		expenses_qs = expenses_qs.filter(expense_date__gte=from_date)
		appointments_qs = appointments_qs.filter(created_at__date__gte=from_date)
		products_qs = products_qs.filter(created_at__date__gte=from_date)
	if to_date:
		invoices_qs = invoices_qs.filter(created_at__date__lte=to_date)
		clients_qs = clients_qs.filter(created_at__date__lte=to_date)
		payments_qs = payments_qs.filter(paid_at__date__lte=to_date)
		refunds_qs = refunds_qs.filter(refunded_at__date__lte=to_date)
		expenses_qs = expenses_qs.filter(expense_date__lte=to_date)
		appointments_qs = appointments_qs.filter(created_at__date__lte=to_date)
		products_qs = products_qs.filter(created_at__date__lte=to_date)

	show_income = _can_view_income(request.user)
	payments_total = payments_qs.aggregate(total=Sum("amount")).get("total") or 0
	refunds_total = refunds_qs.aggregate(total=Sum("amount")).get("total") or 0
	revenue_total = (payments_total - refunds_total) if show_income else None
	service_cost_total = None
	service_profit_total = None
	product_cost_total = None
	product_profit_total = None
	if show_income:
		records = ProfitRecord.objects.select_related("invoice").all()
		if branch_id is not None:
			records = records.filter(invoice__branch_id=branch_id)
		if from_date:
			records = records.filter(invoice__created_at__date__gte=from_date)
		if to_date:
			records = records.filter(invoice__created_at__date__lte=to_date)
		aggs = records.aggregate(
			service_cost=Sum("service_cost_total"),
			service_profit=Sum("service_profit_total"),
			product_cost=Sum("product_cost_total"),
			product_profit=Sum("product_profit_total"),
		)
		service_cost_total = aggs.get("service_cost") or Decimal("0.00")
		service_profit_total = aggs.get("service_profit") or Decimal("0.00")
		product_cost_total = aggs.get("product_cost") or Decimal("0.00")
		product_profit_total = aggs.get("product_profit") or Decimal("0.00")
	expenses_total = expenses_qs.aggregate(total=Sum("amount")).get("total") or 0
	invoiced_total = sum((inv.total() for inv in invoices_qs), Decimal("0.00")) if show_income else None
	outstanding_total = sum((inv.outstanding_balance() for inv in invoices_qs), Decimal("0.00")) if show_income else None

	rows = [
		["Clients Total", str(clients_qs.count())],
		["Clients Active", str(clients_qs.filter(status=Client.Status.ACTIVE).count())],
		["Invoices Total", str(invoices_qs.count())],
		["Invoices Paid", str(invoices_qs.filter(status=Invoice.Status.PAID).count())],
		["Expenses", _money(expenses_total)],
		["Appointments Upcoming", str(appointments_qs.filter(scheduled_for__gte=now).count())],
		["Products Total", str(products_qs.count())],
		["Products Low Stock", str(products_qs.filter(stock_quantity__lte=F("low_stock_threshold")).count())],
	]
	if show_income:
		rows = [
			["Clients Total", str(clients_qs.count())],
			["Clients Active", str(clients_qs.filter(status=Client.Status.ACTIVE).count())],
			["Invoices Total", str(invoices_qs.count())],
			["Invoices Paid", str(invoices_qs.filter(status=Invoice.Status.PAID).count())],
			["Total Invoiced", _money(invoiced_total)],
			["Revenue (Net)", _money(revenue_total)],
			["Refunds", _money(refunds_total)],
			["Product Cost (COGS)", _money(product_cost_total)],
			["Product Gross Profit", _money(product_profit_total)],
			["Service Charges (COGS)", _money(service_cost_total)],
			["Service Gross Profit", _money(service_profit_total)],
			["Expenses", _money(expenses_total)],
			["Outstanding Balances", _money(outstanding_total)],
			["Net Profit", _money(revenue_total - expenses_total - service_cost_total - product_cost_total)],
			["Appointments Upcoming", str(appointments_qs.filter(scheduled_for__gte=now).count())],
			["Products Total", str(products_qs.count())],
			["Products Low Stock", str(products_qs.filter(stock_quantity__lte=F("low_stock_threshold")).count())],
		]
	extra_inline = _get_str(request, "inline")
	return _pdf_response(
		title="Reports Summary",
		header=["Metric", "Value"],
		rows=rows,
		filename="reports.pdf",
		inline=extra_inline in {"1", "true", "yes", "on"},
	)


@login_required
def users_view(request):
	guard = _require_admin(request)
	if guard is not None:
		return guard

	User = get_user_model()
	users = User.objects.all().order_by("email")
	# Managing Director cannot see admin/superusers.
	if not getattr(request.user, "is_superuser", False) and _role(request.user) == "managing_director":
		users = users.exclude(role="admin").exclude(is_superuser=True)
	return render(request, "modules/users.html", {"users": users})


@login_required
def add_user(request):
	guard = _require_admin(request)
	if guard is not None:
		return guard

	from accounts.forms import AdminUserCreateForm

	form = AdminUserCreateForm(request.POST or None)
	# Managing Director cannot create admin users.
	if not getattr(request.user, "is_superuser", False) and _role(request.user) == "managing_director":
		try:
			form.fields["role"].choices = [c for c in form.fields["role"].choices if c[0] != "admin"]
		except Exception:
			pass
	if request.method == "POST" and form.is_valid():
		user_obj = form.save(commit=False)
		if not getattr(request.user, "is_superuser", False) and _role(request.user) == "managing_director":
			if getattr(user_obj, "role", None) == "admin" or getattr(user_obj, "is_superuser", False):
				messages.error(request, "You cannot create an Admin user.")
				return render(request, "modules/add_user.html", {"form": form})
			user_obj.is_staff = False
			user_obj.is_superuser = False
		user_obj.save()
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

	# Managing Director cannot access admin/superuser accounts.
	if not getattr(request.user, "is_superuser", False) and _role(request.user) == "managing_director":
		if getattr(user_obj, "is_superuser", False) or getattr(user_obj, "role", None) == "admin":
			messages.error(request, "User not found.")
			return redirect("users")

	form = AdminUserUpdateForm(request.POST or None, instance=user_obj)
	# Managing Director cannot promote users to Admin.
	if not getattr(request.user, "is_superuser", False) and _role(request.user) == "managing_director":
		try:
			form.fields["role"].choices = [c for c in form.fields["role"].choices if c[0] != "admin"]
		except Exception:
			pass
	if request.method == "POST" and form.is_valid():
		updated = form.save(commit=False)
		if not getattr(request.user, "is_superuser", False) and _role(request.user) == "managing_director":
			if getattr(updated, "role", None) == "admin" or getattr(updated, "is_superuser", False):
				messages.error(request, "You cannot modify an Admin user.")
				return render(request, "modules/edit_user.html", {"form": form, "user_obj": user_obj})
		updated.save()
		messages.success(request, "User updated successfully.")
		return redirect("users")
	return render(request, "modules/edit_user.html", {"form": form, "user_obj": user_obj})


@login_required
def delete_user(request, user_id: int):
	guard = _require_admin(request)
	if guard is not None:
		return guard

	if request.method != "POST":
		return redirect("users")

	User = get_user_model()
	user_obj = User.objects.filter(id=user_id).first()
	if user_obj is None:
		messages.error(request, "User not found.")
		return redirect("users")

	if user_obj.id == request.user.id:
		messages.error(request, "You cannot delete your own account.")
		return redirect("users")

	# Managing Director cannot delete admin/superusers.
	if not getattr(request.user, "is_superuser", False) and _role(request.user) == "managing_director":
		if getattr(user_obj, "is_superuser", False) or getattr(user_obj, "role", None) == "admin":
			messages.error(request, "You cannot delete an Admin user.")
			return redirect("users")

	# Never delete superusers from the portal UI.
	if getattr(user_obj, "is_superuser", False):
		messages.error(request, "You cannot delete an Admin user.")
		return redirect("users")

	user_obj.delete()
	messages.success(request, "User deleted successfully.")
	return redirect("users")


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


@login_required
def global_search(request):
	"""Global search across all modules in the system."""
	query = request.GET.get('q', '').strip()
	results = {
		'clients': [],
		'invoices': [],
		'receipts': [],
		'quotations': [],
		'appointments': [],
		'services': [],
		'inventory': [],
		'expenses': [],
		'documents': [],
		'sales': [],
		'reports': [],
	}

	if query:
		from clients.models import Client
		from invoices.models import Invoice, Payment
		from sales.models import Quotation
		from appointments.models import Appointment
		from services.models import Service
		from inventory.models import Product
		from expenses.models import Expense
		from documents.models import Document
		from reports.models import ProfitRecord

		# Search clients
		try:
			results['clients'] = Client.objects.filter(
				Q(full_name__icontains=query) |
				Q(company_name__icontains=query) |
				Q(email__icontains=query) |
				Q(phone__icontains=query) |
				Q(contact_person__icontains=query)
			)[:10]
		except Exception:
			results['clients'] = []

		# Search invoices
		try:
			results['invoices'] = Invoice.objects.filter(
				Q(number__icontains=query) |
				Q(client__full_name__icontains=query) |
				Q(client__company_name__icontains=query) |
				Q(notes__icontains=query)
			).select_related('client')[:10]
		except Exception:
			results['invoices'] = []

		# Search receipts
		try:
			results['receipts'] = Payment.objects.filter(
				Q(receipt_number__icontains=query) |
				Q(invoice__client__full_name__icontains=query) |
				Q(invoice__client__company_name__icontains=query) |
				Q(reference__icontains=query) |
				Q(notes__icontains=query)
			).select_related('invoice__client')[:10]
		except Exception:
			results['receipts'] = []

		# Search quotations
		try:
			results['quotations'] = Quotation.objects.filter(
				Q(number__icontains=query) |
				Q(client__full_name__icontains=query) |
				Q(client__company_name__icontains=query) |
				Q(notes__icontains=query)
			).select_related('client')[:10]
		except Exception:
			results['quotations'] = []

		# Search appointments
		try:
			results['appointments'] = Appointment.objects.filter(
				Q(notes__icontains=query) |
				Q(appointment_type__icontains=query) |
				Q(status__icontains=query) |
				Q(meeting_mode__icontains=query) |
				Q(client__full_name__icontains=query) |
				Q(client__company_name__icontains=query) |
				Q(assigned_to__email__icontains=query)
			).select_related('client')[:10]
		except Exception:
			results['appointments'] = []

		# Search services
		try:
			results['services'] = Service.objects.filter(
				Q(name__icontains=query) |
				Q(description__icontains=query) |
				Q(category__name__icontains=query)
			)[:10]
		except Exception:
			results['services'] = []

		# Search inventory
		try:
			results['inventory'] = Product.objects.filter(
				Q(name__icontains=query) |
				Q(description__icontains=query) |
				Q(category__name__icontains=query) |
				Q(category__category_type__icontains=query) |
				Q(sku__icontains=query)
			)[:10]
		except Exception:
			results['inventory'] = []

		# Search expenses
		try:
			results['expenses'] = Expense.objects.filter(
				Q(description__icontains=query) |
				Q(category__icontains=query) |
				Q(reference__icontains=query)
			)[:10]
		except Exception:
			results['expenses'] = []

		# Search documents
		try:
			results['documents'] = Document.objects.filter(
				Q(title__icontains=query) |
				Q(notes__icontains=query) |
				Q(doc_type__icontains=query) |
				Q(doc_type_other__icontains=query) |
				Q(client__full_name__icontains=query) |
				Q(client__company_name__icontains=query)
			)[:10]
		except Exception:
			results['documents'] = []

		# Sales: no standalone Sale model in this project; keep the section empty.
		results['sales'] = []

		# Reports (profit records)
		try:
			results['reports'] = ProfitRecord.objects.filter(
				Q(invoice__number__icontains=query) |
				Q(invoice__client__full_name__icontains=query) |
				Q(invoice__client__company_name__icontains=query)
			).select_related('invoice', 'invoice__client')[:10]
		except Exception:
			results['reports'] = []

	# Count total results
	total_results = sum(len(results[category]) for category in results)

	context = {
		'query': query,
		'results': results,
		'total_results': total_results,
	}

	return render(request, 'modules/global_search.html', context)


# Backwards-compatible alias (older code referenced `dashboard`)
dashboard = dashboard_view
