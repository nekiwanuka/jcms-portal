from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import EmailLoginForm, OtpVerifyForm, ShiftIdentityForm
from .models import LoginAuditLog, OneTimePassword


class SafePasswordResetView(auth_views.PasswordResetView):
	"""Password reset that surfaces email backend failures.

	On shared hosts SMTP is often misconfigured; Django's default behavior is to raise,
	causing a 500. Here we show a user-friendly message instead.
	"""

	def form_valid(self, form):
		try:
			return super().form_valid(form)
		except Exception as exc:
			# Don't leak internals in production.
			if getattr(settings, "DEBUG", False):
				messages.error(self.request, f"Unable to send reset email: {exc}")
			else:
				messages.error(
					self.request,
					"Unable to send reset email right now. Please contact support.",
				)
			return self.render_to_response(self.get_context_data(form=form))


def _get_client_ip(request):
	xff = request.META.get("HTTP_X_FORWARDED_FOR")
	if xff:
		return xff.split(",")[0].strip()
	return request.META.get("REMOTE_ADDR")


def _lockout_key(email: str, ip: str | None) -> str:
	return f"login:lock:{email}:{ip or 'na'}"


def _failcount_key(email: str, ip: str | None) -> str:
	return f"login:fail:{email}:{ip or 'na'}"


def _is_locked_out(email: str, ip: str | None) -> bool:
	return cache.get(_lockout_key(email, ip)) is True


def _register_failed_attempt(email: str, ip: str | None):
	key = _failcount_key(email, ip)
	fails = cache.get(key, 0) + 1
	cache.set(key, fails, timeout=settings.LOGIN_LOCKOUT_SECONDS)
	if fails >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
		cache.set(_lockout_key(email, ip), True, timeout=settings.LOGIN_LOCKOUT_SECONDS)


def _send_otp_email(to_email: str, code: str):
	subject = "Your Jambas Imaging OTP"
	message = f"Your OTP code is: {code}\n\nIt expires in {settings.OTP_TTL_SECONDS // 60} minutes."
	send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)


def login_view(request):
	if request.user.is_authenticated:
		if request.session.get("otp_verified") is True:
			return redirect("dashboard")
		return redirect("accounts:otp_verify")

	form = EmailLoginForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		email = form.cleaned_data["email"].strip().lower()
		password = form.cleaned_data["password"]
		ip = _get_client_ip(request)

		if _is_locked_out(email, ip):
			messages.error(request, "Too many failed attempts. Please try again later.")
			return render(request, "accounts/login.html", {"form": form})

		user = authenticate(request, username=email, password=password)
		if user is None:
			_register_failed_attempt(email, ip)
			LoginAuditLog.objects.create(
				user=None,
				email=email,
				ip_address=ip,
				user_agent=request.META.get("HTTP_USER_AGENT", ""),
				success=False,
			)
			messages.error(request, "Invalid credentials")
		else:
			login(request, user)
			request.session["otp_verified"] = False

			otp, code = OneTimePassword.issue_for_user(user)
			try:
				_send_otp_email(user.email, code)
				messages.info(request, "An OTP has been sent to your email.")
			except Exception:
				otp.delete()
				logout(request)
				messages.error(request, "Unable to send OTP email. Please contact support.")
				return redirect("accounts:login")

			return redirect("accounts:otp_verify")

	return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
	logout(request)
	return redirect("accounts:login")


def otp_verify_view(request):
	if not request.user.is_authenticated:
		return redirect("accounts:login")

	if request.session.get("otp_verified") is True:
		return redirect("dashboard")

	form = OtpVerifyForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		code = form.cleaned_data["code"].strip()

		otp = (
			OneTimePassword.objects.filter(user=request.user, verified_at__isnull=True)
			.order_by("-created_at")
			.first()
		)
		if otp is None or otp.is_expired:
			messages.error(request, "OTP expired. Please resend OTP.")
			return redirect("accounts:otp_verify")

		if otp.verify_attempts >= settings.OTP_MAX_VERIFY_ATTEMPTS:
			messages.error(request, "Too many invalid OTP attempts. Please resend OTP.")
			return redirect("accounts:otp_verify")

		if otp.verify(code):
			otp.verified_at = timezone.now()
			otp.save(update_fields=["verified_at"])
			request.session["otp_verified"] = True
			if not (
				request.session.get("prepared_by_name")
				and request.session.get("issued_by_name")
				and request.session.get("signed_by_name")
			):
				return redirect("accounts:shift_identity")
			return redirect("dashboard")

		messages.error(request, "Invalid OTP")

	return render(request, "accounts/otp_verify.html", {"form": form})


def otp_resend_view(request):
	if not request.user.is_authenticated:
		return redirect("accounts:login")

	otp = (
		OneTimePassword.objects.filter(user=request.user, verified_at__isnull=True)
		.order_by("-created_at")
		.first()
	)

	if otp and otp.last_sent_at:
		seconds_since = int((timezone.now() - otp.last_sent_at).total_seconds())
		if seconds_since < settings.OTP_RESEND_SECONDS:
			messages.warning(request, "Please wait before resending OTP.")
			return redirect("accounts:otp_verify")

	otp, code = OneTimePassword.issue_for_user(request.user)
	try:
		_send_otp_email(request.user.email, code)
		messages.info(request, "A new OTP has been sent to your email.")
	except Exception:
		otp.delete()
		messages.error(request, "Unable to send OTP email. Please contact support.")

	return redirect("accounts:otp_verify")


def _collect_name_suggestions() -> list[str]:
	"""Return a small list of existing real-name suggestions."""
	from django.contrib.auth import get_user_model
	from invoices.models import Invoice

	User = get_user_model()
	suggestions: set[str] = set()
	suggestions.add("JAMBAS IMAGING (U) LTD")
	try:
		for name in User.objects.exclude(full_name="").values_list("full_name", flat=True).distinct()[:200]:
			name = (name or "").strip()
			if name:
				suggestions.add(name)
	except Exception:
		pass
	try:
		for name in Invoice.objects.exclude(prepared_by_name="").values_list("prepared_by_name", flat=True).distinct()[:200]:
			name = (name or "").strip()
			if name:
				suggestions.add(name)
		for name in Invoice.objects.exclude(signed_by_name="").values_list("signed_by_name", flat=True).distinct()[:200]:
			name = (name or "").strip()
			if name:
				suggestions.add(name)
	except Exception:
		pass
	return sorted(suggestions)[:200]


def shift_identity_view(request):
	"""Set Prepared By / Issued By / Approved By for the current shift.

	Stored in session so users don't retype names on every document.
	"""
	if not request.user.is_authenticated:
		return redirect("accounts:login")
	if request.session.get("otp_verified") is not True:
		return redirect("accounts:otp_verify")

	initial = {
		"prepared_by_name": request.session.get("prepared_by_name", ""),
		"issued_by_name": request.session.get("issued_by_name", "") or request.session.get("prepared_by_name", ""),
		"signed_by_name": request.session.get("signed_by_name", ""),
	}
	form = ShiftIdentityForm(request.POST or None, initial=initial)
	name_suggestions = _collect_name_suggestions()

	if request.method == "POST" and form.is_valid():
		prepared = (form.cleaned_data.get("prepared_by_name") or "").strip()
		issued = (form.cleaned_data.get("issued_by_name") or "").strip()
		signed = (form.cleaned_data.get("signed_by_name") or "").strip()
		request.session["prepared_by_name"] = prepared
		request.session["issued_by_name"] = issued
		request.session["signed_by_name"] = signed
		messages.success(request, "Shift identity updated.")
		return redirect("dashboard")

	return render(
		request,
		"accounts/shift_identity.html",
		{
			"form": form,
			"name_suggestions": name_suggestions,
		},
	)
