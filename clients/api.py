from rest_framework import viewsets

from accounts.models import User
from accounts.permissions import RolePermission

from .models import Client
from .serializers import ClientSerializer


class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer

    def get_permissions(self):
        # Most staff can read; managers/admin can manage; sales can create/update clients.
        return [
            RolePermission(
                allow_read={
                    User.Role.ADMIN,
                    User.Role.MANAGER,
                    User.Role.SALES,
                    User.Role.STORE,
                    User.Role.ACCOUNTANT,
                },
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES},
            )
        ]
