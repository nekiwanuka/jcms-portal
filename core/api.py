from rest_framework import viewsets

from accounts.models import User
from accounts.permissions import RolePermission

from .models import Branch
from .serializers import BranchSerializer


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer

    def get_permissions(self):
        # Branch management is typically admin/manager.
        return [
            RolePermission(
                allow_read={User.Role.ADMIN, User.Role.MANAGER},
                allow_write={User.Role.ADMIN, User.Role.MANAGER},
            )
        ]
