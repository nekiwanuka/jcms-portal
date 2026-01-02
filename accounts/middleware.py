from django.shortcuts import redirect
from django.urls import reverse


class OtpRequiredMiddleware:
    """For authenticated users, require OTP verification after login.

    Allows access to login/logout/otp endpoints without OTP.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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

        return self.get_response(request)
