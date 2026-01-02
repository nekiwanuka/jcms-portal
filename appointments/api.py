from rest_framework import viewsets

from accounts.models import User
from accounts.permissions import RolePermission

from .models import Appointment
from .serializers import AppointmentSerializer


class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.select_related("client").all()
    serializer_class = AppointmentSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

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
                allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES, User.Role.STORE},
            )
        ]
