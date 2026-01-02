from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .admin_forms import AdminUserChangeForm, AdminUserCreationForm
from .models import LoginAuditLog, OneTimePassword, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
	add_form = AdminUserCreationForm
	form = AdminUserChangeForm
	model = User

	ordering = ("email",)
	list_display = ("email", "full_name", "role", "is_active", "is_staff")
	list_filter = ("role", "is_active", "is_staff", "is_superuser")
	search_fields = ("email", "full_name", "phone")
	readonly_fields = ("last_login", "date_joined")

	fieldsets = (
		(None, {"fields": ("email", "password")}),
		("Profile", {"fields": ("full_name", "phone", "role")}),
		(
			"Permissions",
			{"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
		),
		("Important dates", {"fields": ("last_login", "date_joined")}),
	)
	add_fieldsets = (
		(
			None,
			{
				"classes": ("wide",),
				"fields": (
					"email",
					"full_name",
					"phone",
					"role",
					"is_active",
					"is_staff",
					"is_superuser",
					"password1",
					"password2",
				),
			},
		),
	)


@admin.register(OneTimePassword)
class OneTimePasswordAdmin(admin.ModelAdmin):
	list_display = ("user", "created_at", "expires_at", "last_sent_at", "verified_at", "verify_attempts")
	list_filter = ("verified_at",)
	search_fields = ("user__email",)


@admin.register(LoginAuditLog)
class LoginAuditLogAdmin(admin.ModelAdmin):
	list_display = ("email", "success", "ip_address", "created_at")
	list_filter = ("success",)
	search_fields = ("email", "ip_address")
