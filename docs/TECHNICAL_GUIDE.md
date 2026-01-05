# Technical Guide (Jambas Imaging Business Management System)

This document is for developers and the technical team.

## 1) Overview

This is a Django 4.2 LTS application for managing:

- Clients + KYC
- Quotations
- Invoices + payments/receipts + refunds
- Inventory (products, categories, suppliers, stock movements)
- Services (service catalog, categories)
- Documents archive (per client / linked to invoices/payments)
- Appointments
- Reports (income/profit KPIs)

UI is mostly server-rendered Django templates (Bootstrap). Some pages use small JavaScript helpers for auto-fill and live calculations.

## 2) Tech Stack

- Python 3.11
- Django 4.2 LTS
- Django REST Framework (JSON API)
- django-filter
- SQLite (default local dev) or PostgreSQL/MySQL via env vars

Dependencies: see `requirements.txt`.

## 3) Project Layout

Key folders:

- `jambas/` – project settings/urls/asgi/wsgi
- `core/` – shared utilities, Branch model, dashboard, reports views, audit logging
- `accounts/` – custom user model, OTP middleware, permissions
- `clients/` – client/KYC
- `sales/` – quotations
- `invoices/` – invoices, items, payments, refunds
- `inventory/` – products, categories, suppliers, stock movements
- `services/` – services catalog and service categories
- `documents/` – document uploads and archive
- `appointments/` – scheduling + reminder command
- `reports/` – profit ledger model (recorded profit)
- `templates/` – UI templates
- `static/` and `staticfiles/` – assets + collected static
- `media/` – uploaded files

## 4) Environment Configuration

Settings are read from `.env` (and optional `.env.local` overrides) in the project root (same folder as `manage.py`).

Important settings (from `jambas/settings.py`):

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG` (`1`/`0`)
- `DJANGO_ALLOWED_HOSTS` (comma-separated)
- `DJANGO_CSRF_TRUSTED_ORIGINS` (comma-separated)

Database:

- `DB_ENGINE` (default sqlite)
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `SQLITE_TIMEOUT` (helps on Windows)

Email:

- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- TLS/SSL: `EMAIL_USE_TLS`, `EMAIL_USE_SSL`
- Aliases supported: `MAIL_*`

OTP/security:

- `OTP_LENGTH`, `OTP_TTL_SECONDS`, `OTP_RESEND_SECONDS`, `OTP_MAX_VERIFY_ATTEMPTS`
- `LOGIN_MAX_FAILED_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS`

Business defaults:

- `DEFAULT_CURRENCY` (default `UGX`)
- `DEFAULT_VAT_RATE` (default `0.18`)

Appointments reminders:

- `APPOINTMENT_REMINDER_LEAD_MINUTES`
- `APPOINTMENT_REMINDER_WINDOW_MINUTES`

## 5) Local Development (Windows)

From the workspace root:

- Run migrations:
  - `./.venv/Scripts/python.exe manage.py migrate`

- Create admin user:
  - `./.venv/Scripts/python.exe manage.py createsuperuser`

- Run server:
  - `./.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000`

- Run checks:
  - `./.venv/Scripts/python.exe manage.py check`

### Reset test data

- Backup DB and reset data:
  - `./.venv/Scripts/python.exe manage.py reset_data`

- Reset data and wipe uploaded media:
  - `./.venv/Scripts/python.exe manage.py reset_data --include-media`

## 6) Deployment Notes (cPanel + Passenger)

This repo includes `passenger_wsgi.py` and is designed for cPanel “Setup Python App”.

Typical deployment steps:

1. Create the Python App (Python 3.11).
2. Set startup file to `passenger_wsgi.py` and entry point `application`.
3. Upload project so `manage.py` and `passenger_wsgi.py` are in app root.
4. Configure `.env` in the app root.
5. Install dependencies inside the Passenger venv.
6. Run migrations: `manage.py migrate`.
7. Collect static: `manage.py collectstatic --noinput`.
8. Create an admin user.

## 7) Authentication and Authorization

### Login + OTP

- Login uses email + password.
- After successful password auth, OTP is generated and emailed.
- `accounts.middleware.OtpRequiredMiddleware` blocks access until OTP verified.

### Roles / Admin-only actions

The system uses a custom `accounts.User` and helper checks in `core.views`.

Admin-only actions (enforced in server views):

- Delete clients
- Refund payments / delete payments / delete refunds
- View financial reports
- Cancel invoices

If you extend roles, keep enforcement server-side (templates should only hide buttons; the view must enforce).

## 8) Core Business Flows

### 8.1 Clients

- List clients, create, edit.
- Admin can delete a client (protected if referenced).

### 8.2 Services

- Services are a shared catalog for invoices and quotations.
- Each service has sales price and a service charge (cost).
- Profit per unit is derived.

### 8.3 Inventory (Products)

- Product stores sales price and cost price.
- Live “profit per unit / total cost / total profit” calculation is shown on add/edit product pages.
- Stock levels and low-stock thresholds are tracked.

### 8.4 Quotations

- Quotation items can be products or services.
- When quotation is approved, it may convert into an invoice.

### 8.5 Invoices and Payments

- Invoice items can be products or services.
- Payments can be partial.
- Refunds are admin-only.

#### Profit recording (Profit Ledger)

Profit is recorded **independently** when an invoice becomes PAID.

- Model: `reports.ProfitRecord` (one-to-one with an invoice)
- Trigger: invoice status refresh after payments
- If invoice later becomes not-paid (due to payment deletion/refund changes), the ledger record is removed/updated accordingly.

This supports reporting based on recorded profits rather than recalculating from line items each time.

## 9) Reporting

Reports aggregate:

- Revenue (net of refunds)
- Product COGS and product gross profit
- Service charges (COGS) and service gross profit
- Expenses
- Net profit

Financial reports are admin-only.

## 10) REST API

The internal API is under `/api/` and returns JSON (Browsable API disabled by default). It supports product/service lookups for UI auto-fill.

## 11) Troubleshooting

- Static files missing in production: run `collectstatic --noinput` and verify web server serves `/static/`.
- OTP email not sending: verify SMTP env vars and that `DEFAULT_FROM_EMAIL` is valid.
- SQLite locked on Windows: increase `SQLITE_TIMEOUT`.

## 12) Extending the System

Recommended patterns:

- Put workflow actions in server-side views with explicit permission checks.
- Avoid hard deletes for business documents; prefer “cancel” or “deactivate” to preserve history.
- Snapshot costs on invoice items if historical profit accuracy is required.
