from rest_framework.permissions import BasePermission, SAFE_METHODS


class RolePermission(BasePermission):
    """Simple role-based permission helper.

    Use:
      RolePermission(allow_read={...}, allow_write={...})
    """

    def __init__(self, allow_read=None, allow_write=None):
        self.allow_read = set(allow_read or [])
        self.allow_write = set(allow_write or [])

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True

        role = getattr(user, "role", None)
        # Managing Director has full portal-level permissions (API side).
        if role == "managing_director":
            return True
        if request.method in SAFE_METHODS:
            return role in self.allow_read or role in self.allow_write
        return role in self.allow_write
