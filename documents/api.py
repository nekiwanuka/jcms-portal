from rest_framework import viewsets

from accounts.models import User
from accounts.permissions import RolePermission

from .models import Document
from .serializers import DocumentSerializer


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.select_related("client").all()
    serializer_class = DocumentSerializer

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={
                    User.Role.ADMIN,
                    User.Role.MANAGER,
                    User.Role.SALES,
                    User.Role.STORE,
                    User.Role.ACCOUNTANT,
                },
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES, User.Role.STORE, User.Role.ACCOUNTANT},
            )
        ]
