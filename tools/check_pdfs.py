import os
import sys
from decimal import Decimal


def main() -> int:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jambas.settings")

    import django  # noqa: PLC0415

    django.setup()

    from invoices.models import Invoice, Payment  # noqa: PLC0415
    from sales.models import Quotation  # noqa: PLC0415
    from clients.models import Client  # noqa: PLC0415
    from core.views import (  # noqa: PLC0415
        _build_invoice_pdf_bytes,
        _build_receipt_pdf_bytes,
        _build_quotation_pdf_bytes,
    )
    from invoices.models import InvoiceItem  # noqa: PLC0415
    from sales.models import QuotationItem  # noqa: PLC0415

    invoice = Invoice.objects.order_by("-id").first()
    quotation = Quotation.objects.order_by("-id").first()
    payment = Payment.objects.order_by("-id").first()

    created = {
        "client": None,
        "quotation": None,
        "quotation_items": [],
        "invoice": None,
        "invoice_items": [],
        "payment": None,
    }

    if not invoice or not quotation or not payment:
        client = Client.objects.create(
            client_type=Client.ClientType.COMPANY,
            company_name="PDF Check Ltd",
            contact_person="Test User",
            phone="+256000000000",
            email="pdfcheck@example.com",
            physical_address="Kampala",
        )
        created["client"] = client

        quotation = Quotation.objects.create(
            client=client,
            category=Quotation.Category.IT,
            notes="Temporary quotation created by tools/check_pdfs.py",
        )
        created["quotation"] = quotation
        created["quotation_items"].append(
            QuotationItem.objects.create(
                quotation=quotation,
                description="IT Support Services",
                quantity=Decimal("1.00"),
                unit_price=Decimal("100000.00"),
            )
        )

        invoice = Invoice.objects.create(
            client=client,
            notes="Temporary invoice created by tools/check_pdfs.py",
            prepared_by_name="System",
            signed_by_name="System",
        )
        created["invoice"] = invoice
        created["invoice_items"].append(
            InvoiceItem.objects.create(
                invoice=invoice,
                description="Printing & Branding Materials",
                quantity=Decimal("2.00"),
                unit_price=Decimal("50000.00"),
            )
        )

        payment = Payment.objects.create(
            invoice=invoice,
            method=Payment.Method.CASH,
            amount=Decimal("50000.00"),
            reference="TEMP",
            notes="Temporary payment created by tools/check_pdfs.py",
        )
        created["payment"] = payment

    print("invoice:", bool(invoice))
    print("quotation:", bool(quotation))
    print("payment:", bool(payment))

    if invoice:
        data = _build_invoice_pdf_bytes(invoice)
        print("invoice pdf bytes:", len(data))

    if quotation:
        data = _build_quotation_pdf_bytes(quotation, proforma=False)
        print("quotation pdf bytes:", len(data))
        data = _build_quotation_pdf_bytes(quotation, proforma=True)
        print("proforma pdf bytes:", len(data))

    if payment:
        data = _build_receipt_pdf_bytes(payment)
        print("receipt pdf bytes:", len(data))

    print("OK")

    # Clean up any temporary objects we created.
    if created["payment"] is not None:
        created["payment"].delete()
    for item in created["invoice_items"]:
        item.delete()
    if created["invoice"] is not None:
        created["invoice"].delete()
    for item in created["quotation_items"]:
        item.delete()
    if created["quotation"] is not None:
        created["quotation"].delete()
    if created["client"] is not None:
        created["client"].delete()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
