from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import Client

from .forms import BidForm
from .models import Bid


class BidFormTests(TestCase):
	def setUp(self):
		self.client_obj = Client.objects.create(
			client_type=Client.ClientType.INDIVIDUAL,
			full_name="Test Client",
		)

	def test_deadline_not_in_past(self):
		form = BidForm(
			data={
				"client": self.client_obj.id,
				"title": "Tender 1",
				"reference_number": "REF-1",
				"submission_method": Bid.SubmissionMethod.EMAIL,
				"category": Bid.Category.OTHER,
				"category_other": "Custom",
				"amount": "100.00",
				"closing_date": (timezone.localdate() - timedelta(days=1)).isoformat(),
				"notes": "",
			}
		)
		self.assertFalse(form.is_valid())
		self.assertIn("closing_date", form.errors)

	def test_document_must_be_pdf(self):
		non_pdf = SimpleUploadedFile(
			"not-a-pdf.txt",
			b"hello",
			content_type="text/plain",
		)
		form = BidForm(
			data={
				"client": self.client_obj.id,
				"title": "Tender 2",
				"reference_number": "REF-2",
				"submission_method": Bid.SubmissionMethod.EMAIL,
				"category": Bid.Category.OTHER,
				"category_other": "Custom",
				"amount": "100.00",
				"closing_date": (timezone.localdate() + timedelta(days=1)).isoformat(),
				"notes": "",
			},
			files={"document": non_pdf},
		)
		self.assertFalse(form.is_valid())
		self.assertIn("document", form.errors)

	def test_locked_bid_cannot_be_edited_via_form(self):
		bid = Bid.objects.create(
			client=self.client_obj,
			title="Locked",
			closing_date=timezone.localdate() + timedelta(days=7),
			status=Bid.Status.SUBMITTED,
		)
		form = BidForm(
			data={
				"client": self.client_obj.id,
				"title": "Locked edited",
				"reference_number": "",
				"submission_method": Bid.SubmissionMethod.EMAIL,
				"category": Bid.Category.OTHER,
				"category_other": "Custom",
				"amount": "0.00",
				"closing_date": (timezone.localdate() + timedelta(days=7)).isoformat(),
				"notes": "",
			},
			instance=bid,
		)
		self.assertFalse(form.is_valid())
		self.assertIn("__all__", form.errors)


class BidModelTests(TestCase):
	def setUp(self):
		self.client_obj = Client.objects.create(
			client_type=Client.ClientType.INDIVIDUAL,
			full_name="Test Client",
		)

	def test_bid_number_auto_increments(self):
		year = timezone.localdate().year
		b1 = Bid.objects.create(
			client=self.client_obj,
			title="Bid 1",
			closing_date=timezone.localdate() + timedelta(days=1),
		)
		b2 = Bid.objects.create(
			client=self.client_obj,
			title="Bid 2",
			closing_date=timezone.localdate() + timedelta(days=2),
		)
		self.assertTrue(b1.bid_number.startswith(f"BID-{year}-"))
		self.assertTrue(b2.bid_number.startswith(f"BID-{year}-"))
		self.assertNotEqual(b1.bid_number, b2.bid_number)
		self.assertTrue(b1.bid_number.endswith("00001"))
		self.assertTrue(b2.bid_number.endswith("00002"))


class BidViewsTests(TestCase):
	def setUp(self):
		User = get_user_model()
		self.user = User.objects.create_user(email="tester@example.com", password="pass12345")
		self.client.force_login(self.user)
		session = self.client.session
		session["otp_verified"] = True
		session["prepared_by_name"] = "Tester"
		session["issued_by_name"] = "Tester"
		session["signed_by_name"] = "Tester"
		session.save()

		self.client_obj = Client.objects.create(
			client_type=Client.ClientType.INDIVIDUAL,
			full_name="Test Client",
		)

	def test_edit_locked_bid_redirects(self):
		bid = Bid.objects.create(
			client=self.client_obj,
			title="Locked",
			closing_date=timezone.localdate() + timedelta(days=7),
			status=Bid.Status.LOST,
			created_by=self.user,
		)
		resp = self.client.get(reverse("edit_bid", args=[bid.id]))
		self.assertEqual(resp.status_code, 302)

	def test_add_bid_past_deadline_shows_error(self):
		resp = self.client.post(
			reverse("add_bid"),
			data={
				"client": self.client_obj.id,
				"title": "Tender",
				"reference_number": "",
				"submission_method": Bid.SubmissionMethod.EMAIL,
				"category": Bid.Category.OTHER,
				"category_other": "Custom",
				"amount": "10.00",
				"closing_date": (timezone.localdate() - timedelta(days=30)).isoformat(),
				"notes": "",
			},
			follow=True,
		)
		self.assertEqual(Bid.objects.count(), 0)
		self.assertEqual(resp.status_code, 200)
		self.assertTemplateUsed(resp, "bids/add_bid.html")
		self.assertIn("form", resp.context)
		self.assertIn("closing_date", resp.context["form"].errors)
