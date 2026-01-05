from django.urls import path

from . import views

urlpatterns = [
    # Make the dashboard the homepage
    path("", views.dashboard_view, name="dashboard"),

    # Frontend module pages (template-rendered, login-protected)
    path("clients/", views.clients_view, name="clients"),
    path("clients/add/", views.add_client, name="add_client"),
	path("clients/<int:client_id>/edit/", views.edit_client, name="edit_client"),
	path("clients/<int:client_id>/delete/", views.delete_client, name="delete_client"),
	path("clients/<int:client_id>/", views.client_history, name="client_history"),
    path("clients/export/csv/", views.export_clients_csv, name="export_clients_csv"),
    path("clients/export/pdf/", views.export_clients_pdf, name="export_clients_pdf"),
    path("invoices/", views.invoices_view, name="invoices"),
    path("invoices/add/", views.add_invoice, name="add_invoice"),
    path("invoices/<int:invoice_id>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:invoice_id>/edit/", views.edit_invoice, name="edit_invoice"),
    path("invoices/<int:invoice_id>/cancel/", views.cancel_invoice, name="cancel_invoice"),
    path("invoices/<int:invoice_id>/sign/", views.sign_invoice, name="sign_invoice"),
    path("invoices/<int:invoice_id>/send/", views.send_invoice, name="send_invoice"),
    path("invoices/<int:invoice_id>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("invoices/<int:invoice_id>/items/add/", views.add_invoice_item, name="add_invoice_item"),
    path("invoices/<int:invoice_id>/items/<int:item_id>/edit/", views.edit_invoice_item, name="edit_invoice_item"),
    path("invoices/<int:invoice_id>/items/<int:item_id>/delete/", views.delete_invoice_item, name="delete_invoice_item"),
    path("invoices/<int:invoice_id>/payments/add/", views.add_invoice_payment, name="add_invoice_payment"),
    path(
        "invoices/<int:invoice_id>/payments/<int:payment_id>/refund/",
        views.refund_payment,
        name="refund_payment",
    ),
    path(
        "invoices/<int:invoice_id>/payments/<int:payment_id>/delete/",
        views.delete_invoice_payment,
        name="delete_invoice_payment",
    ),
    path(
        "invoices/<int:invoice_id>/refunds/<int:refund_id>/delete/",
        views.delete_payment_refund,
        name="delete_payment_refund",
    ),
    path(
        "invoices/<int:invoice_id>/payments/<int:payment_id>/receipt/pdf/",
        views.payment_receipt_pdf,
        name="payment_receipt_pdf",
    ),
    path(
        "invoices/<int:invoice_id>/payments/<int:payment_id>/receipt/send/",
        views.send_payment_receipt,
        name="send_payment_receipt",
    ),
    path("invoices/export/csv/", views.export_invoices_csv, name="export_invoices_csv"),
    path("invoices/export/pdf/", views.export_invoices_pdf, name="export_invoices_pdf"),

	# Receipts (payments register)
	path("receipts/", views.receipts_view, name="receipts"),
    path("receipts/<int:payment_id>/reverse/", views.reverse_receipt, name="reverse_receipt"),

    # Quotations (procurement workflow)
    path("quotations/", views.quotations_view, name="quotations"),
    path("quotations/add/", views.add_quotation, name="add_quotation"),
    path("quotations/<int:quotation_id>/", views.quotation_detail, name="quotation_detail"),
    path("quotations/<int:quotation_id>/edit/", views.edit_quotation, name="edit_quotation"),
    path("quotations/<int:quotation_id>/pdf/", views.quotation_pdf, name="quotation_pdf"),
    path("quotations/<int:quotation_id>/proforma/pdf/", views.proforma_pdf, name="proforma_pdf"),
    path("quotations/<int:quotation_id>/send/", views.send_quotation, name="send_quotation"),
    path("quotations/<int:quotation_id>/items/add/", views.add_quotation_item, name="add_quotation_item"),
    path(
        "quotations/<int:quotation_id>/items/<int:item_id>/edit/",
        views.edit_quotation_item,
        name="edit_quotation_item",
    ),
    path(
        "quotations/<int:quotation_id>/items/<int:item_id>/delete/",
        views.delete_quotation_item,
        name="delete_quotation_item",
    ),
    path("quotations/<int:quotation_id>/status/<str:status>/", views.set_quotation_status, name="set_quotation_status"),
    path("quotations/<int:quotation_id>/cancel/", views.cancel_quotation, name="cancel_quotation"),
    path("quotations/<int:quotation_id>/convert/", views.convert_quotation_to_invoice, name="convert_quotation_to_invoice"),
    path("inventory/", views.inventory_view, name="inventory"),
    path("inventory/add/", views.add_inventory, name="add_inventory"),
	path("inventory/<int:product_id>/edit/", views.edit_inventory, name="edit_inventory"),
	path("inventory/<int:product_id>/delete/", views.delete_inventory, name="delete_inventory"),
    path("inventory/categories/", views.inventory_categories_view, name="inventory_categories"),
    path("inventory/categories/add/", views.add_inventory_category, name="add_inventory_category"),
    path(
        "inventory/categories/<int:category_id>/edit/",
        views.edit_inventory_category,
        name="edit_inventory_category",
    ),
    path(
        "inventory/categories/<int:category_id>/delete/",
        views.delete_inventory_category,
        name="delete_inventory_category",
    ),
	path("inventory/stock-movements/", views.stock_movements_view, name="stock_movements"),
	path("inventory/products/<int:product_id>/stock/", views.adjust_stock, name="adjust_stock"),
    path("inventory/export/csv/", views.export_inventory_csv, name="export_inventory_csv"),
    path("inventory/export/pdf/", views.export_inventory_pdf, name="export_inventory_pdf"),

    # Suppliers (inventory)
    path("inventory/suppliers/", views.suppliers_view, name="suppliers"),
    path("inventory/suppliers/add/", views.add_supplier, name="add_supplier"),
    path("inventory/suppliers/<int:supplier_id>/", views.supplier_detail, name="supplier_detail"),
    path("inventory/suppliers/<int:supplier_id>/edit/", views.edit_supplier, name="edit_supplier"),
    path("inventory/supplier-prices/add/", views.add_supplier_price, name="add_supplier_price"),
    path("inventory/supplier-prices/<int:price_id>/edit/", views.edit_supplier_price, name="edit_supplier_price"),
    path("inventory/supplier-prices/<int:price_id>/delete/", views.delete_supplier_price, name="delete_supplier_price"),
    path("inventory/products/<int:product_id>/prices/", views.product_price_compare, name="product_price_compare"),

    # Services
    path("services/", views.services_view, name="services"),
    path("services/add/", views.add_service, name="add_service"),
    path("services/<int:service_id>/edit/", views.edit_service, name="edit_service"),
    path("services/<int:service_id>/delete/", views.delete_service, name="delete_service"),
    path("services/categories/", views.service_categories_view, name="service_categories"),
    path("services/categories/add/", views.add_service_category, name="add_service_category"),
    path("services/categories/<int:category_id>/edit/", views.edit_service_category, name="edit_service_category"),
    path("services/categories/<int:category_id>/delete/", views.delete_service_category, name="delete_service_category"),
    path("expenses/", views.expenses_view, name="expenses"),
    path("expenses/add/", views.add_expense, name="add_expense"),
    path("expenses/export/csv/", views.export_expenses_csv, name="export_expenses_csv"),
    path("expenses/export/pdf/", views.export_expenses_pdf, name="export_expenses_pdf"),
    path("appointments/", views.appointments_view, name="appointments"),
    path("appointments/add/", views.add_appointment, name="add_appointment"),
    path("appointments/export/csv/", views.export_appointments_csv, name="export_appointments_csv"),
    path("appointments/export/pdf/", views.export_appointments_pdf, name="export_appointments_pdf"),
    path("reports/", views.reports_view, name="reports"),
	path("reports/export/csv/", views.export_reports_csv, name="export_reports_csv"),
	path("reports/export/pdf/", views.export_reports_pdf, name="export_reports_pdf"),

    # System (admin-only)
    path("system/users/", views.users_view, name="users"),
    path("system/users/add/", views.add_user, name="add_user"),
    path("system/users/<int:user_id>/edit/", views.edit_user, name="edit_user"),
    path("system/audit/", views.audit_logs_view, name="audit_logs"),
]
