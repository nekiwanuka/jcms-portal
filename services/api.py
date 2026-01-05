from rest_framework import viewsets

from accounts.models import User
from accounts.permissions import RolePermission

from .models import Service
from .serializers import ServiceSerializer


class ServiceViewSet(viewsets.ModelViewSet):
	queryset = Service.objects.all()
	serializer_class = ServiceSerializer

	def get_permissions(self):
		return [
			RolePermission(
				allow_read={
					User.Role.ADMIN,
					User.Role.MANAGER,
					User.Role.SALES,
					User.Role.ACCOUNTANT,
				},
				allow_write={User.Role.ADMIN, User.Role.MANAGER, User.Role.SALES},
			)
		]
