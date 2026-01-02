from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings

from .forms import DocumentForm
from .models import Document


def _get_str(request, key: str) -> str:
	return (request.GET.get(key) or "").strip()


@login_required
def documents_archive(request):
	qs = Document.objects.select_related(
		"client",
		"uploaded_by",
		"related_quotation",
		"related_invoice",
		"related_payment",
		"related_bid",
	).all()
	q = _get_str(request, "q")
	client_id = _get_str(request, "client")
	doc_type = _get_str(request, "type")
	date_from = _get_str(request, "from")
	date_to = _get_str(request, "to")

	if q:
		qs = qs.filter(Q(title__icontains=q) | Q(client__full_name__icontains=q) | Q(client__company_name__icontains=q))
	if client_id.isdigit():
		qs = qs.filter(client_id=int(client_id))
	if doc_type:
		qs = qs.filter(doc_type=doc_type)
	if date_from:
		qs = qs.filter(uploaded_at__date__gte=date_from)
	if date_to:
		qs = qs.filter(uploaded_at__date__lte=date_to)

	context = {
		"documents": qs[:100],
		"doc_type_choices": Document.DocumentType.choices,
		"filters": {"q": q, "client": client_id, "type": doc_type, "from": date_from, "to": date_to},
	}
	return render(request, "documents/archive.html", context)


@login_required
def upload_document(request):
	from core.audit import log_event
	from core.models import AuditEvent

	initial = {}
	client_id = _get_str(request, "client")
	quotation_id = _get_str(request, "quotation")
	bid_id = _get_str(request, "bid")
	if client_id.isdigit():
		initial["client"] = int(client_id)
	if quotation_id.isdigit():
		initial["related_quotation"] = int(quotation_id)
	if bid_id.isdigit():
		initial["related_bid"] = int(bid_id)

	if request.method == "POST":
		form = DocumentForm(request.POST, request.FILES, initial=initial)
		if form.is_valid():
			doc = form.save(commit=False)
			doc.uploaded_by = request.user
			# If a parent context was provided in querystring, enforce it.
			if client_id.isdigit():
				doc.client_id = int(client_id)
			if quotation_id.isdigit():
				doc.related_quotation_id = int(quotation_id)
			if bid_id.isdigit():
				doc.related_bid_id = int(bid_id)
			doc.save()
			log_event(
				action=AuditEvent.Action.DOCUMENT_UPLOADED,
				actor=request.user,
				entity=doc,
				client=doc.client,
				summary=f"{doc.doc_type_label}: {doc.title}",
				meta={
					"doc_type": doc.doc_type,
					"related_bid_id": doc.related_bid_id,
					"related_quotation_id": doc.related_quotation_id,
				},
			)
			messages.success(request, "Document uploaded.")
			return redirect("documents_archive")
	else:
		form = DocumentForm(initial=initial)

	return render(request, "documents/upload.html", {"form": form})


@login_required
def download_document(request, doc_id: int):
	doc = get_object_or_404(Document.objects.select_related("client"), pk=doc_id)
	if not doc.file:
		raise Http404("File not found")
	try:
		response = FileResponse(doc.file.open("rb"), as_attachment=True)
		extra_inline = _get_str(request, "inline")
		if extra_inline in {"1", "true", "yes", "on"}:
			response["Content-Disposition"] = f'inline; filename="{doc.file.name.split("/")[-1]}"'
		return response
	except FileNotFoundError as exc:
		raise Http404("File missing") from exc


@login_required
def send_document(request, doc_id: int):
	"""Email a document to the associated client (explicit action).

	This is intentionally NOT triggered on save/upload.
	"""
	from django.core.mail import EmailMultiAlternatives

	if request.method != "POST":
		return redirect("documents_archive")

	doc = get_object_or_404(Document.objects.select_related("client"), pk=doc_id)
	client_email = getattr(doc.client, "email", "") if doc.client_id else ""
	client_email = (client_email or "").strip()
	if not client_email:
		messages.error(request, "Client does not have an email address.")
		return redirect("documents_archive")
	if not doc.file:
		messages.error(request, "This document has no file attached.")
		return redirect("documents_archive")

	subject = f"Document: {doc.title or 'Attachment'}"
	body = (
		f"Dear {doc.client},\n\n"
		f"Please find attached the document: {doc.title or '(Untitled)'}\n"
		f"Type: {doc.doc_type_label}\n\n"
		"Regards,\nJambas Imaging"
	)

	msg = EmailMultiAlternatives(
		subject=subject,
		body=body,
		from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
		to=[client_email],
	)
	try:
		filename = (doc.file.name or "document").split("/")[-1]
		doc.file.open("rb")
		msg.attach(filename, doc.file.read(), "application/octet-stream")
		doc.file.close()
		msg.send(fail_silently=False)
		messages.success(request, "Document sent to client.")
	except Exception:
		messages.error(request, "Failed to send document email. Check email settings.")

	return redirect("documents_archive")
