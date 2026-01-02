# Jambas Imaging Business Management System (Django)

Django-based business management system for Jambas Imaging (Uganda).

System documentation: see [docs/SYSTEM.md](docs/SYSTEM.md).

## Local Development (Windows)

1. Activate venv
   - PowerShell: `C:\Users\NEKIWANUKA\Desktop\jcms_Portal\.venv\Scripts\Activate.ps1`

2. Create `.env`
   - Copy: `.env.example` → `.env`

3. Run migrations
   - `C:/Users/NEKIWANUKA/Desktop/jcms_Portal/.venv/Scripts/python.exe manage.py migrate`

4. Start server
   - `C:/Users/NEKIWANUKA/Desktop/jcms_Portal/.venv/Scripts/python.exe manage.py runserver`

### Login + OTP

- Login URL: `/accounts/login/`
- In local dev, OTP emails are printed to the terminal (console email backend).

Security note:
- Do not commit `.env` (it is already in `.gitignore`). If credentials/secrets were ever shared or pasted into chat/logs, rotate them.

### Create an admin user

- `C:/Users/NEKIWANUKA/Desktop/jcms_Portal/.venv/Scripts/python.exe manage.py createsuperuser`

## Environment Variables

See `.env.example`. Key settings:

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`
- Database: `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- Email: `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- OTP: `OTP_LENGTH`, `OTP_TTL_SECONDS`, `OTP_RESEND_SECONDS`, `OTP_MAX_VERIFY_ATTEMPTS`
- Throttling: `LOGIN_MAX_FAILED_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS`

## cPanel Shared Hosting Deployment (Passenger WSGI)

This project is designed to work on cPanel shared hosting using **cPanel “Setup Python App”** (Passenger).

### 1) Create the Python App

In cPanel:

- **Software → Setup Python App**
- Create a new app
  - Python version: `3.11` (or highest available)
  - Application root: e.g. `jambas_app`
  - Application URL: choose your domain/subdomain
  - Application startup file: `passenger_wsgi.py`
  - Application entry point: `application`

Upload the project files into the **Application root** (so `manage.py` and `passenger_wsgi.py` sit in the app root).

### 2) Install dependencies

Use the cPanel Python App terminal/pip interface:

- Install from `requirements.txt`

Notes:
- For **PostgreSQL** you will usually need `psycopg2` or `psycopg2-binary`.
- For **MySQL** you will often need `mysqlclient` (may require system libs). On shared hosting, MySQL is commonly available.

### 3) Configure `.env`

Create a `.env` file in the **application root** (same folder as `manage.py`).

Minimum recommended production values:

- `DJANGO_DEBUG=0`
- `DJANGO_SECRET_KEY=<long-random-secret>`
- `DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com`
- Set DB settings for your cPanel database
- Set SMTP credentials:
  - `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
  - `EMAIL_HOST=...`
  - `EMAIL_HOST_USER=info@jambasimaging.com` (or `sales@jambasimaging.com` depending on your sending policy)
  - `EMAIL_HOST_PASSWORD=...`

### 4) Static + Media

This project uses:

- `STATIC_ROOT=staticfiles/`
- `MEDIA_ROOT=media/`

Run:

- `python manage.py collectstatic`

Then configure your web server (via cPanel) to serve:

- `/static/` → `staticfiles/`
- `/media/` → `media/`

On many cPanel setups, static files are served from `public_html`. If your Python app root is not inside `public_html`, you may need to:

- Copy/symlink `staticfiles/` and `media/` into `public_html` and map URLs accordingly.

### 5) Database migrations

Run:

- `python manage.py migrate`

### 6) Create admin user

Run:

- `python manage.py createsuperuser --email admin@jambasimaging.com`

### 7) Security checklist (production)

- Set `DJANGO_DEBUG=0`
- Ensure correct `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`
- Use strong `DJANGO_SECRET_KEY`
- Use SMTP with TLS
- Restrict `/media/` access if you store sensitive KYC documents (recommended)

## Project Layout

- `accounts/` – custom user, OTP, audit logs, password reset, OTP middleware
- `clients/` – client/KYC
- `inventory/` – products, suppliers, stock movements
- `sales/` – quotations
- `invoices/` – invoices, payments
- `appointments/` – appointment scheduling
- `documents/` – document uploads organized by client
- `core/` – shared models (e.g. Branch) and dashboard
