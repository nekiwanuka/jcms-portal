# Jambas Imaging Business Management System

This document explains what the system does, how it is structured, and how the main flows work.

## Overview

This is a Django-based business management system for Jambas Imaging (Uganda). It supports:

- Clients + KYC
- Quotations + sales
- Invoicing + payments
- Inventory management
- Appointments
- Document management
- OTP-based login security
- Audit logs
- Internal REST API (for future mobile app)

The UI is primarily **Django Templates + Bootstrap**, while **Django Admin** is used for back-office management.

## Tech Stack

- Django 4.2 LTS
- Django REST Framework (JSON API; browsable UI may be disabled in production)
- django-filter (filter backends)
- python-dotenv (reads `.env` locally; optional)
- SQLite for local dev (default). PostgreSQL/MySQL supported via env vars.

## Project Structure

- `jambas/` – Django project (settings/urls/wsgi)
- `accounts/` – Custom user model, OTP, password reset
- `core/` – Shared models (Branch), dashboard, audit events
- `clients/` – Client + KYC data
- `inventory/` – Suppliers, product categories, products, stock movements
- `sales/` – Quotations, quotation items
- `invoices/` – Invoices, invoice items, payments
- `appointments/` – Appointment scheduling
- `documents/` – Document uploads (organized by client)
- `templates/` – HTML templates
- `static/` – Static files
- `media/` – Uploaded files

## Roles and Access

Users are stored in the custom model `accounts.User`.

Roles implemented:

- Admin
- Manager
- Sales Staff
- Store Manager
- Accountant

Role-based access is enforced in two places:

- **Django Admin permissions** (staff/superuser flags + groups if you choose to extend)
- **API permissions** via `accounts.permissions.RolePermission`

## Audit Trail

The system stores a lightweight audit trail in `core.AuditEvent` for key workflow events (e.g., quotation status changes, document uploads).

## Authentication & OTP Flow

### Login

1. User signs in at `/accounts/login/` using email + password.
2. If credentials are valid:
   - A One-Time Password (OTP) is generated.
   - OTP is emailed to the user.
   - Session flag `otp_verified = False` is stored.
3. User is redirected to `/accounts/otp/`.

### OTP Verification

1. User enters the OTP.
2. If valid and not expired:
   - Session flag `otp_verified = True`.
   - User is redirected to the dashboard (`/`).

### OTP Enforcement

`accounts.middleware.OtpRequiredMiddleware` blocks access to normal pages for logged-in users until OTP is verified.

Allowed (without OTP):

- `/accounts/otp/`
- `/accounts/otp/resend/`
- `/accounts/logout/`
- `/admin/` (admin is intentionally exempt)

### Security Controls

- OTP expiry: configured via `OTP_TTL_SECONDS`
- OTP resend cooldown: `OTP_RESEND_SECONDS`
- OTP verify attempts: `OTP_MAX_VERIFY_ATTEMPTS`
- Login lockout for bad passwords:
  - `LOGIN_MAX_FAILED_ATTEMPTS`
  - `LOGIN_LOCKOUT_SECONDS`

### Password Reset

Users can reset password via:

- `/accounts/password-reset/`

Emails are sent using the configured SMTP settings.

## Modules (Data Model Summary)

### Core (multi-branch ready)

- `core.Branch`
  - Optional foreign key from most models so the system can be expanded to multi-branch later.

### Clients

- `clients.Client`
  - Individual/Company
  - Contact person, phone, email, address
  - TIN/NIN
  - Status: Prospect/Active

### Inventory

- `inventory.Supplier`
- `inventory.ProductCategory` (Printing / IT / Medical / PPE)
- `inventory.Product`
  - SKU, pricing, stock quantity, low-stock threshold
- `inventory.StockMovement`
  - Stock-in / Stock-out logs

### Sales (Quotations)

- `sales.Quotation`
  - Auto-numbered (e.g. `Q-2025-00001`)
  - VAT calculations
- `sales.QuotationItem`

### Invoices & Payments

- `invoices.Invoice`
  - Auto-numbered (e.g. `INV-2025-00001`)
  - Supports partial payments
  - Has helpers: `amount_paid()` and `outstanding_balance()`
- `invoices.InvoiceItem`
- `invoices.Payment`
  - Methods: Cash / Bank / Mobile Money

### Appointments

- `appointments.Appointment`
  - Types: Consultation / Printing job / IT support
  - Status: Pending / Confirmed / Completed / Cancelled
  - Staff assignment
  - Meeting mode: Physical / Google Meet / WhatsApp (stored per appointment)

## Appointment Reminders

The system supports simple email reminders for upcoming appointments (sent to both the client email and the assigned staff email, if available).

How it works:

- A scheduled job runs a management command periodically.
- The command finds appointments that are `pending` or `confirmed` within the reminder window.
- It sends an email (HTML + text fallback) and marks `reminder_sent_at` to avoid duplicates.

### Run Manually (Local)

- `C:/Users/NEKIWANUKA/Desktop/jcms_Portal/.venv/Scripts/python.exe manage.py send_appointment_reminders --dry-run`

### Recommended Cron (cPanel)

Run every 30 minutes:

- `cd /path/to/jcms_Portal && /path/to/python manage.py send_appointment_reminders`

### Configuration

These environment variables control the default timing:

- `APPOINTMENT_REMINDER_LEAD_MINUTES` (default `1440` = 24 hours)
- `APPOINTMENT_REMINDER_WINDOW_MINUTES` (default `30`)

### Documents

- `documents.Document`
  - Types: Invoice / Quotation / Contract / ID / Other
  - Upload path is organized by client ID

## UI Pages

- Dashboard: `/`
- Login: `/accounts/login/`
- OTP: `/accounts/otp/`
- Django Admin: `/admin/`

Most operational CRUD can be managed in Django Admin initially.

## REST API

The API is mounted at:

- `/api/`

It uses DRF viewsets and a router. Primary endpoints:

- `/api/branches/`
- `/api/clients/`
- `/api/suppliers/`
- `/api/product-categories/`
- `/api/products/`
- `/api/stock-movements/`
- `/api/quotations/`
- `/api/quotation-items/`
- `/api/invoices/`
- `/api/invoice-items/`
- `/api/payments/`
- `/api/appointments/`
- `/api/documents/`

## Email Configuration

Django supports SMTP via `EMAIL_*` env vars. The project also supports `MAIL_*` env vars as aliases.

Typical SSL SMTP (port 465):

- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST=...`
- `EMAIL_PORT=465`
- `EMAIL_USE_SSL=1`
- `EMAIL_USE_TLS=0`

## How to Run (Local)

Use the venv python (important):

- `C:/Users/NEKIWANUKA/Desktop/jcms_Portal/.venv/Scripts/python.exe manage.py migrate`
- `C:/Users/NEKIWANUKA/Desktop/jcms_Portal/.venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000`

Then:

- Visit `http://127.0.0.1:8000/accounts/login/`

## Deployment (cPanel)

See `README.md` for Passenger/cPanel notes and recommended production settings.
