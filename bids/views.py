from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BidForm
from .models import Bid


@login_required
def bids_list(request):
	qs = Bid.objects.select_related("client", "created_by", "quotation").all()
	q = (request.GET.get("q") or "").strip()
	status = (request.GET.get("status") or "").strip()
	category = (request.GET.get("category") or "").strip()

	if q:
		qs = qs.filter(
			Q(bid_number__icontains=q)
			| Q(title__icontains=q)
			| Q(reference_number__icontains=q)
			| Q(tender_reference__icontains=q)
			| Q(quotation__number__icontains=q)
			| Q(client__full_name__icontains=q)
			| Q(client__company_name__icontains=q)
		)
	if status:
		qs = qs.filter(status=status)
	if category:
		qs = qs.filter(category=category)

	context = {
		"bids": qs[:100],
		"counts": {
			"active": qs.filter(status__in={Bid.Status.DRAFT, Bid.Status.SUBMITTED, Bid.Status.UNDER_REVIEW}).count(),
			"won": qs.filter(status=Bid.Status.WON).count(),
			"lost": qs.filter(status=Bid.Status.LOST).count(),
		},
		"filters": {"q": q, "status": status, "category": category},
		"status_choices": Bid.Status.choices,
		"category_choices": Bid.Category.choices,
	}
	return render(request, "bids/bids_list.html", context)


@login_required
def add_bid(request):
	if request.method == "POST":
		form = BidForm(request.POST, request.FILES)
		if form.is_valid():
			bid = form.save(commit=False)
			bid.created_by = request.user
			bid.status = Bid.Status.DRAFT
			bid.outcome = "pending"
			bid.save()
			messages.success(request, "Bid created.")
			return redirect("bids_list")
	else:
		form = BidForm()
	return render(request, "bids/add_bid.html", {"form": form})


@login_required
def view_bid(request, bid_id: int):
	from documents.models import Document

	bid = get_object_or_404(Bid.objects.select_related("client", "created_by", "submitted_by", "quotation"), pk=bid_id)
	docs = Document.objects.filter(related_bid=bid).order_by("-uploaded_at", "-version")
	return render(request, "bids/view_bid.html", {"bid": bid, "documents": docs[:20]})


@login_required
def set_bid_status(request, bid_id: int, status: str):
	from sales.models import Quotation

	bid = get_object_or_404(Bid.objects.select_related("quotation"), pk=bid_id)
	allowed = {
		Bid.Status.DRAFT,
		Bid.Status.SUBMITTED,
		Bid.Status.UNDER_REVIEW,
		Bid.Status.WON,
		Bid.Status.LOST,
		Bid.Status.CANCELLED,
	}
	if request.method != "POST":
		return redirect("view_bid", bid_id=bid.id)
	if status not in allowed:
		messages.error(request, "Invalid status change.")
		return redirect("view_bid", bid_id=bid.id)

	# Update status only (editing the full bid remains locked after submission).
	bid.status = status
	if status == Bid.Status.SUBMITTED and not bid.submitted_by:
		bid.submitted_by = request.user

	# Keep legacy outcome roughly in sync.
	if status == Bid.Status.WON:
		bid.outcome = "won"
	elif status == Bid.Status.LOST:
		bid.outcome = "lost"
	else:
		bid.outcome = "pending"

	bid.save(update_fields=["status", "submitted_by", "outcome"])

	# If a bid is WON and linked to a quotation, treat it as approved.
	if status == Bid.Status.WON and bid.quotation_id:
		try:
			quote = bid.quotation
			if quote and quote.status not in {Quotation.Status.CONVERTED}:
				if quote.status not in {Quotation.Status.ACCEPTED}:
					quote.status = Quotation.Status.ACCEPTED
					quote.save(update_fields=["status"])
		except Exception:
			pass

	messages.success(request, "Bid status updated.")
	return redirect("view_bid", bid_id=bid.id)


@login_required
def edit_bid(request, bid_id: int):
	bid = get_object_or_404(Bid.objects.select_related("client"), pk=bid_id)
	if bid.is_locked:
		messages.warning(request, "Submitted tenders are read-only and cannot be edited.")
		return redirect("view_bid", bid_id=bid.id)

	if request.method == "POST":
		form = BidForm(request.POST, request.FILES, instance=bid)
		if form.is_valid():
			form.save()
			messages.success(request, "Bid updated.")
			return redirect("view_bid", bid_id=bid.id)
	else:
		form = BidForm(instance=bid)

	return render(request, "bids/edit_bid.html", {"bid": bid, "form": form})
