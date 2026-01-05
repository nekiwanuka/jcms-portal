from rest_framework import viewsets

from accounts.models import User
from accounts.permissions import RolePermission

from .models import Quotation, QuotationItem
from .serializers import QuotationItemSerializer, QuotationSerializer


class QuotationViewSet(viewsets.ModelViewSet):
    queryset = Quotation.objects.select_related("client").all()
    serializer_class = QuotationSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES, User.Role.ACCOUNTANT},
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES},
            )
        ]


class QuotationItemViewSet(viewsets.ModelViewSet):
    queryset = QuotationItem.objects.select_related("quotation", "product", "service").all()
    serializer_class = QuotationItemSerializer

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES, User.Role.ACCOUNTANT},
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES},
            )
        ]
