# Jambas Imaging Business Management System (Django)

Django-based business management system for Jambas Imaging (Uganda).

Documentation:

- System overview: [docs/SYSTEM.md](docs/SYSTEM.md)
- Technical team guide: [docs/TECHNICAL_GUIDE.md](docs/TECHNICAL_GUIDE.md)
- End-user guide: [docs/USER_GUIDE.md](docs/USER_GUIDE.md)

## Local Development (Windows)

1. Activate venv
   - PowerShell: `C:\Users\NEKIWANUKA\Desktop\jcms_Portal\venv\Scripts\Activate.ps1`

2. Create `.env`
   - Copy: `.env.example` → `.env`

3. Run migrations
   - `C:/Users/NEKIWANUKA/Desktop/jcms_Portal/venv/Scripts/python.exe manage.py migrate`

4. Start server
   - `C:/Users/NEKIWANUKA/Desktop/jcms_Portal/venv/Scripts/python.exe manage.py runserver`

### Reset test data (fresh start)

If you entered data only for testing and want to start over:

- Reset database (backs up `db.sqlite3` into `backups/` first):
   - `./.venv/Scripts/python.exe ./manage.py reset_data`

- Reset database **and** delete uploaded files under `media/`:
   - `./.venv/Scripts/python.exe ./manage.py reset_data --include-media`

After resetting, re-create an admin account:

- `./.venv/Scripts/python.exe ./manage.py createsuperuser`

### Login + OTP


Security note:

### Create an admin user


## Environment Variables

See `.env.example`. Key settings:


## cPanel Shared Hosting Deployment (Passenger WSGI)

This project is designed to work on cPanel shared hosting using **cPanel “Setup Python App”** (Passenger).

### 1) Create the Python App

In cPanel:

  - Python version: `3.11` (or highest available)
  - Application root: e.g. `jambas_app`
  - Application URL: choose your domain/subdomain
  - Application startup file: `passenger_wsgi.py`
  - Application entry point: `application`

Upload the project files into the **Application root** (so `manage.py` and `passenger_wsgi.py` sit in the app root).

### 2) Install dependencies

Use the cPanel Python App terminal/pip interface:


Notes:

### 3) Configure `.env`

Create a `.env` file in the **application root** (same folder as `manage.py`).

Minimum recommended production values:

  - `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
  - `EMAIL_HOST=...`
  - `EMAIL_HOST_USER=info@jambasimaging.com` (or `sales@jambasimaging.com` depending on your sending policy)
  - `EMAIL_HOST_PASSWORD=...`

### 4) Static + Media

This project uses:


Run:


Then configure your web server (via cPanel) to serve:


On many cPanel setups, static files are served from `public_html`. If your Python app root is not inside `public_html`, you may need to:


### 5) Database migrations

Run:


### 6) Create admin user

Run:


### 7) Security checklist (production)


## Project Layout

- `accounts/` – custom user, OTP, audit logs, password reset, OTP middleware
- `clients/` – client/KYC

## cPanel (no SSH) deployment

If cPanel Terminal/SSH is unavailable, you can still deploy using **Setup Python App** + **Git Version Control**.

1) Clone/pull the repo into your chosen folder (recommended: `jcms-portal-repo`).

2) In **Setup Python App** set:
    - Application root: `jcms-portal-repo`
    - Startup file: `passenger_wsgi.py`
    - Entry point: `application`

3) Create your production `.env` in the application root (same folder as `manage.py`).

4) In **Setup Python App** → **Execute Python Script**, run:
    - `tools/cpanel_bootstrap.py`

This script upgrades pip tooling inside the Passenger virtualenv and installs `requirements.txt`.

5) Then run (also via **Execute Python Script**) as needed:
    - `manage.py migrate`
    - `manage.py collectstatic --noinput`
    - `manage.py createsuperuser`

### Troubleshooting

**Broken logo / SVG not showing**

- On some shared hosts, `.svg` can be blocked or served with the wrong MIME type.
- This project now falls back to `static/images/jambas-company-logo.png` automatically if the SVG fails.
- If the image is still broken, your server is not serving `/static/`.
   - Run: `manage.py collectstatic --noinput`
   - Ensure your web server maps `/static/` to the app `staticfiles/` directory.

**Login says “Invalid credentials”**

- Login uses **email + password** (not username).
- If you recently switched databases (SQLite ↔ Postgres), your admin user might be in a different DB.
- Use these scripts via **Setup Python App → Execute Python Script**:
   - `tools/cpanel_diag.py` (prints DB + lists users)
   - `tools/cpanel_set_password.py` (set env vars `TARGET_EMAIL`, `NEW_PASSWORD` to reset a user password)
- `inventory/` – products, suppliers, stock movements
- `sales/` – quotations
- `invoices/` – invoices, payments
- `appointments/` – appointment scheduling
- `documents/` – document uploads organized by client
- `core/` – shared models (e.g. Branch) and dashboard
