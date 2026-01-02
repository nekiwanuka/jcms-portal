import secrets
import string

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
	def create_user(self, email, password=None, **extra_fields):
		if not email:
			raise ValueError("Email is required")
		email = self.normalize_email(email).lower()
		user = self.model(email=email, **extra_fields)
		user.set_password(password)
		user.save(using=self._db)
		return user

	def create_superuser(self, email, password=None, **extra_fields):
		extra_fields.setdefault("is_staff", True)
		extra_fields.setdefault("is_superuser", True)
		extra_fields.setdefault("is_active", True)
		if extra_fields.get("is_staff") is not True:
			raise ValueError("Superuser must have is_staff=True")
		if extra_fields.get("is_superuser") is not True:
			raise ValueError("Superuser must have is_superuser=True")
		return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
	class Role(models.TextChoices):
		ADMIN = "admin", "Admin"
		MANAGER = "manager", "Manager"
		SALES = "sales", "Sales Staff"
		STORE = "store", "Store Manager"
		ACCOUNTANT = "accountant", "Accountant"

	email = models.EmailField(unique=True)
	full_name = models.CharField(max_length=255, blank=True)
	phone = models.CharField(max_length=50, blank=True)

	role = models.CharField(max_length=20, choices=Role.choices, default=Role.SALES)

	is_active = models.BooleanField(default=True)
	is_staff = models.BooleanField(default=False)
	date_joined = models.DateTimeField(default=timezone.now)

	objects = UserManager()

	USERNAME_FIELD = "email"
	REQUIRED_FIELDS = []

	def __str__(self):
		return self.email


def _generate_numeric_code(length: int) -> str:
	alphabet = string.digits
	return "".join(secrets.choice(alphabet) for _ in range(length))


class OneTimePassword(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps")
	code_hash = models.CharField(max_length=128)

	created_at = models.DateTimeField(auto_now_add=True)
	expires_at = models.DateTimeField()
	last_sent_at = models.DateTimeField(null=True, blank=True)
	verified_at = models.DateTimeField(null=True, blank=True)

	verify_attempts = models.PositiveIntegerField(default=0)

	class Meta:
		indexes = [
			models.Index(fields=["user", "created_at"]),
			models.Index(fields=["expires_at"]),
		]

	@property
	def is_expired(self) -> bool:
		return timezone.now() >= self.expires_at

	@property
	def is_verified(self) -> bool:
		return self.verified_at is not None

	@classmethod
	def issue_for_user(cls, user):
		code = _generate_numeric_code(settings.OTP_LENGTH)
		expires_at = timezone.now() + timezone.timedelta(seconds=settings.OTP_TTL_SECONDS)
		otp = cls.objects.create(
			user=user,
			code_hash=make_password(code),
			expires_at=expires_at,
			last_sent_at=timezone.now(),
		)
		return otp, code

	def verify(self, code: str) -> bool:
		if self.is_expired or self.is_verified:
			return False
		self.verify_attempts += 1
		self.save(update_fields=["verify_attempts"])
		return check_password(code, self.code_hash)


class LoginAuditLog(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	email = models.EmailField(blank=True)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	user_agent = models.TextField(blank=True)

	success = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"{self.email} @ {self.created_at:%Y-%m-%d %H:%M:%S} ({'ok' if self.success else 'fail'})"
