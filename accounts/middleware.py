from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages


class OtpRequiredMiddleware:
    """For authenticated users, require OTP verification after login.

    Allows access to login/logout/otp endpoints without OTP.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Managing Director must not access Django admin (/admin).
        try:
            if (
                request.user.is_authenticated
                and getattr(request.user, "role", None) == "managing_director"
                and request.path.startswith("/admin")
            ):
                messages.error(request, "You do not have permission to access the admin site.")
                return redirect("dashboard")
        except Exception:
            pass

        if request.user.is_authenticated:
            otp_verified = bool(request.session.get("otp_verified", False))
            if not otp_verified:
                allowed = {
                    reverse("accounts:otp_verify"),
                    reverse("accounts:otp_resend"),
                    reverse("accounts:logout"),
                }
                if request.path not in allowed and not request.path.startswith("/admin/"):
                    return redirect("accounts:otp_verify")
            else:
                # After OTP, require shift identity for the session.
                if not (
                    request.session.get("prepared_by_name")
                    and request.session.get("issued_by_name")
                    and request.session.get("signed_by_name")
                ):
                    allowed = {
                        reverse("accounts:shift_identity"),
                        reverse("accounts:logout"),
                    }
                    if request.path not in allowed and not request.path.startswith("/admin/"):
                        return redirect("accounts:shift_identity")

        return self.get_response(request)
