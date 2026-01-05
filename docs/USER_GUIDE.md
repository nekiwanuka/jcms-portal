# User Guide (Jambas Imaging Business Management System)

This document is for day-to-day users of the system.

## 1) Getting Started

### Login

1. Open the system URL in your browser.
2. Go to the login page.
3. Sign in using **email + password**.
4. The system will send a One-Time Password (OTP) to your email.
5. Enter the OTP to complete login.

If the OTP expires, use “Resend OTP”.

## 2) Roles and What You Can Do

Everyone can:

- Create and manage clients (create/edit)
- Create quotations and invoices
- Add invoice/quotation items (products or services)
- Record payments (depending on workflow)
- Upload and view documents

Admin-only actions:

- Delete clients
- Make refunds / delete payments / delete refunds
- View financial reports
- Cancel invoices
- Cancel quotations/receipts (where cancellation exists in the UI)

If you cannot see a button, you may not have permission.

## 3) Navigation

Use the left sidebar to access:

- Dashboard
- Clients
- Quotations
- Invoices
- Receipts
- Inventory
- Services
- Appointments
- Documents
- Reports (admin only)

## 4) Clients

### Add a client

1. Open **Clients**.
2. Click **+ Add Client**.
3. Fill in details (Individual or Company).
4. Save.

### Edit a client

- Open the client record (View) then click **Edit**.

### Delete a client (Admin only)

- Open the client record and click **Delete**.

If the client is linked to invoices/quotations/documents, deletion may be blocked.

## 5) Services

Services are items you sell that are not physical stock (e.g. design, installation, printing service).

### Manage services

1. Open **Services**.
2. Add or edit services.

A service includes:

- Category
- Description
- Sales price
- Service charge (cost)
- Profit per unit (auto-calculated)

### Service categories

- Open **Services → Categories** to create and manage categories.

## 6) Inventory (Products)

Products are physical/stock items.

### Add a product

1. Open **Inventory**.
2. Click **+ Add Product**.
3. Enter:
   - Quantity (stock)
   - Cost price (unit cost)
   - Sales price

The system shows:

- Profit per unit
- Total cost (Qty × Cost)
- Total profit (Qty × Profit)

### Product categories

- Open **Inventory → Categories** to create/edit categories.
- Newly created categories will appear in the product category dropdown when you add/edit a product.

## 7) Quotations

Quotations are offers/estimates to a client.

### Create a quotation

1. Open **Quotations** → **Add**.
2. Select client and set VAT/currency if needed.
3. Add items:
   - Choose Product or Service
   - Enter quantity

### Approve and convert

When a quotation is accepted, it can be converted into an invoice.

## 8) Invoices

Invoices are bills sent to clients.

### Create an invoice

1. Open **Invoices** → **+ New Invoice**.
2. Select client and fill invoice details.
3. Save.
4. Open the invoice and add items (products/services).

### Edit an invoice

- You can edit an invoice only before it is **Paid** or **Cancelled**.

### Cancel an invoice (Admin only)

- Open the invoice and click **Cancel**.

Paid invoices cannot be cancelled; use refunds if needed.

### Send invoice

- Use **Send Invoice** to email it (requires email configuration).

## 9) Payments / Receipts

### Record payment

1. Open an invoice.
2. Use the **Record Payment** form.
3. Save.

### Refunds (Admin only)

Admins can record refunds and delete payments/refunds from the invoice screen.

## 10) Documents

Documents can be uploaded and linked to clients (and some documents may be linked to invoices/payments).

Use **Documents** to browse the archive.

## 11) Reports (Admin only)

Reports show:

- Revenue (net)
- Refunds
- Product cost and product gross profit
- Service charges and service gross profit
- Expenses
- Net profit

Profit is recorded when invoices become **Paid**.

## 12) Common Questions

### Why can’t I see the Delete/Refund/Reports buttons?

Those actions are restricted to Admin users.

### Why is an invoice read-only?

Paid or Cancelled invoices are locked to protect accounting history.

### Why is a category not showing?

Refresh the page after adding a new category. Categories appear in dropdowns after the page loads.
