from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
	help = (
		"Reset all application data for a fresh start. "
		"For SQLite, this backs up and deletes the database file, then re-runs migrations. "
		"For other databases, it runs `flush` (destructive)."
	)

	def add_arguments(self, parser):
		parser.add_argument(
			"--include-media",
			action="store_true",
			help="Also delete all uploaded files under MEDIA_ROOT.",
		)
		parser.add_argument(
			"--seed",
			action="store_true",
			help="Also create fresh demo records after reset (admin, quotation, invoice).",
		)
		parser.add_argument(
			"--seed-clients",
			type=int,
			default=5,
			help="Number of demo clients to create when using --seed (default: 5).",
		)
		parser.add_argument(
			"--seed-quotations-per-client",
			type=int,
			default=2,
			help="Quotations per client when using --seed (default: 2).",
		)
		parser.add_argument(
			"--seed-invoices-per-client",
			type=int,
			default=2,
			help="Invoices per client when using --seed (default: 2).",
		)
		parser.add_argument(
			"--seed-payments-per-invoice",
			type=int,
			default=1,
			help="Payments per invoice when using --seed (default: 1).",
		)
		parser.add_argument(
			"--seed-appointments-per-client",
			type=int,
			default=1,
			help="Appointments per client when using --seed (default: 1).",
		)
		parser.add_argument(
			"--seed-documents-per-invoice",
			type=int,
			default=1,
			help="Documents per invoice when using --seed (default: 1).",
		)
		parser.add_argument(
			"--seed-documents-per-payment",
			type=int,
			default=1,
			help="Documents per payment when using --seed (default: 1).",
		)
		parser.add_argument(
			"--seed-admin-email",
			type=str,
			default="admin@jambas.local",
			help="Admin email when using --seed.",
		)
		parser.add_argument(
			"--seed-admin-password",
			type=str,
			default="Admin12345!",
			help="Admin password when using --seed.",
		)
		parser.add_argument(
			"--no-backup",
			action="store_true",
			help="Skip backing up the SQLite DB file before deleting it.",
		)

	def handle(self, *args, **options):
		include_media: bool = bool(options.get("include_media"))
		seed: bool = bool(options.get("seed"))
		seed_clients: int = int(options.get("seed_clients") or 5)
		seed_quotations_per_client: int = int(options.get("seed_quotations_per_client") or 2)
		seed_invoices_per_client: int = int(options.get("seed_invoices_per_client") or 2)
		seed_payments_per_invoice: int = int(options.get("seed_payments_per_invoice") or 1)
		seed_appointments_per_client: int = int(options.get("seed_appointments_per_client") or 1)
		seed_documents_per_invoice: int = int(options.get("seed_documents_per_invoice") or 1)
		seed_documents_per_payment: int = int(options.get("seed_documents_per_payment") or 1)
		seed_admin_email: str = str(options.get("seed_admin_email") or "admin@jambas.local")
		seed_admin_password: str = str(options.get("seed_admin_password") or "Admin12345!")
		no_backup: bool = bool(options.get("no_backup"))

		engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
		name = settings.DATABASES.get("default", {}).get("NAME", "")

		self.stdout.write(self.style.WARNING("This will DELETE all data."))

		if engine.endswith("sqlite3") and name:
			db_path = Path(str(name)).expanduser().resolve()
			# Django may already have an open connection to SQLite. On Windows, an open
			# file cannot be deleted, so close connections first.
			try:
				from django.db import connections
				connections.close_all()
			except Exception:
				pass
			if db_path.exists() and not no_backup:
				backup_dir = (Path(settings.BASE_DIR) / "backups").resolve()
				backup_dir.mkdir(parents=True, exist_ok=True)
				ts = datetime.now().strftime("%Y%m%d_%H%M%S")
				backup_path = backup_dir / f"db.sqlite3.{ts}.bak"
				shutil.copy2(db_path, backup_path)
				self.stdout.write(self.style.SUCCESS(f"Backed up DB to: {backup_path}"))

			# Remove SQLite sidecar files if present.
			for sidecar in (db_path.with_suffix(db_path.suffix + "-wal"), db_path.with_suffix(db_path.suffix + "-shm"), db_path.with_suffix(db_path.suffix + "-journal")):
				try:
					if sidecar.exists():
						sidecar.unlink()
				except Exception:
					pass

			if db_path.exists():
				try:
					db_path.unlink()
					self.stdout.write(self.style.SUCCESS(f"Deleted DB: {db_path}"))
				except PermissionError:
					self.stdout.write(
						self.style.WARNING(
							f"Could not delete DB (file locked): {db_path}. Falling back to flush."
						)
					)
					call_command("flush", interactive=False, verbosity=1)
			else:
				self.stdout.write(self.style.WARNING(f"DB file not found: {db_path}"))

			self.stdout.write("Running migrations...")
			call_command("migrate", interactive=False, verbosity=1)
		else:
			self.stdout.write(
				self.style.WARNING(
					"Non-SQLite database detected; running `flush` (no file backup)."
				)
			)
			call_command("flush", interactive=False, verbosity=1)
			call_command("migrate", interactive=False, verbosity=1)

		if include_media:
			media_root = Path(str(getattr(settings, "MEDIA_ROOT", "")) or "").expanduser().resolve()
			base_dir = Path(settings.BASE_DIR).resolve()
			if not str(media_root):
				self.stdout.write(self.style.WARNING("MEDIA_ROOT is not set; skipping media cleanup."))
			elif media_root == base_dir or media_root == media_root.anchor or len(media_root.parts) <= 2:
				self.stdout.write(self.style.ERROR(f"Refusing to delete unsafe MEDIA_ROOT: {media_root}"))
			else:
				# Only allow deleting media within the project directory.
				try:
					media_root.relative_to(base_dir)
				except Exception:
					self.stdout.write(self.style.ERROR(f"Refusing to delete media outside project: {media_root}"))
				else:
					if media_root.exists():
						for child in media_root.iterdir():
							if child.is_dir():
								shutil.rmtree(child, ignore_errors=True)
							else:
								try:
									child.unlink()
								except Exception:
									pass
						self.stdout.write(self.style.SUCCESS(f"Cleared MEDIA_ROOT: {media_root}"))
					else:
						self.stdout.write(self.style.WARNING(f"MEDIA_ROOT does not exist: {media_root}"))

		self.stdout.write(self.style.SUCCESS("Data reset complete."))
		if seed:
			self.stdout.write("Seeding demo data...")
			call_command(
				"seed_demo",
				admin_email=seed_admin_email,
				admin_password=seed_admin_password,
				clients=seed_clients,
				quotations_per_client=seed_quotations_per_client,
				invoices_per_client=seed_invoices_per_client,
				payments_per_invoice=seed_payments_per_invoice,
				appointments_per_client=seed_appointments_per_client,
				documents_per_invoice=seed_documents_per_invoice,
				documents_per_payment=seed_documents_per_payment,
				verbosity=1,
			)
		else:
			self.stdout.write("Next: create an admin user with `manage.py createsuperuser`.")
