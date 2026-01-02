from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import LoginAuditLog


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    LoginAuditLog.objects.create(
        user=user,
        email=getattr(user, "email", ""),
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        success=True,
    )
