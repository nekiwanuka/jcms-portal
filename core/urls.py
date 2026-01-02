from django.urls import path

from . import views

urlpatterns = [
    # Make the dashboard the homepage
    path("", views.dashboard_view, name="dashboard"),

    # Frontend module pages (template-rendered, login-protected)
    path("clients/", views.clients_view, name="clients"),
    path("clients/add/", views.add_client, name="add_client"),
    path("clients/export/csv/", views.export_clients_csv, name="export_clients_csv"),
    path("clients/export/pdf/", views.export_clients_pdf, name="export_clients_pdf"),
    path("invoices/", views.invoices_view, name="invoices"),
    path("invoices/add/", views.add_invoice, name="add_invoice"),
    path("invoices/<int:invoice_id>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:invoice_id>/sign/", views.sign_invoice, name="sign_invoice"),
    path("invoices/<int:invoice_id>/send/", views.send_invoice, name="send_invoice"),
    path("invoices/<int:invoice_id>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("invoices/<int:invoice_id>/items/add/", views.add_invoice_item, name="add_invoice_item"),
    path("invoices/<int:invoice_id>/items/<int:item_id>/edit/", views.edit_invoice_item, name="edit_invoice_item"),
    path("invoices/<int:invoice_id>/items/<int:item_id>/delete/", views.delete_invoice_item, name="delete_invoice_item"),
    path("invoices/<int:invoice_id>/payments/add/", views.add_invoice_payment, name="add_invoice_payment"),
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
    path("quotations/<int:quotation_id>/convert/", views.convert_quotation_to_invoice, name="convert_quotation_to_invoice"),
    path("inventory/", views.inventory_view, name="inventory"),
    path("inventory/add/", views.add_inventory, name="add_inventory"),
    path("inventory/export/csv/", views.export_inventory_csv, name="export_inventory_csv"),
    path("inventory/export/pdf/", views.export_inventory_pdf, name="export_inventory_pdf"),
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
]
