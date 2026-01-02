from rest_framework import viewsets

from accounts.models import User
from accounts.permissions import RolePermission

from .models import Product, ProductCategory, StockMovement, Supplier
from .serializers import (
    ProductCategorySerializer,
    ProductSerializer,
    StockMovementSerializer,
    SupplierSerializer,
)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={User.Role.ADMIN, User.Role.MANAGER, User.Role.STORE},
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.STORE},
            )
        ]


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={User.Role.ADMIN, User.Role.MANAGER, User.Role.STORE, User.Role.SALES},
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.STORE},
            )
        ]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={
                    User.Role.ADMIN,
                    User.Role.MANAGER,
                    User.Role.STORE,
                    User.Role.SALES,
                    User.Role.ACCOUNTANT,
                },
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.STORE},
            )
        ]


class StockMovementViewSet(viewsets.ModelViewSet):
    queryset = StockMovement.objects.select_related("product").all()
    serializer_class = StockMovementSerializer

    def get_permissions(self):
        return [
            RolePermission(
                allow_read={User.Role.ADMIN, User.Role.MANAGER, User.Role.STORE},
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.STORE},
            )
        ]
