from rest_framework import viewsets

from accounts.models import User
from accounts.permissions import RolePermission

from .models import Invoice, InvoiceItem, Payment
from .serializers import InvoiceItemSerializer, InvoiceSerializer, PaymentSerializer


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.select_related("client").all()
    serializer_class = InvoiceSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES, User.Role.ACCOUNTANT},
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES, User.Role.ACCOUNTANT},
            )
        ]


class InvoiceItemViewSet(viewsets.ModelViewSet):
    queryset = InvoiceItem.objects.select_related("invoice").all()
    serializer_class = InvoiceItemSerializer

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES, User.Role.ACCOUNTANT},
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES, User.Role.ACCOUNTANT},
            )
        ]


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related("invoice").all()
    serializer_class = PaymentSerializer

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={User.Role.ADMIN, User.Role.MANAGER, User.Role.ACCOUNTANT},
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.ACCOUNTANT},
            )
        ]
