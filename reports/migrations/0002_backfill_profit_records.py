from decimal import Decimal

from django.db import migrations


def backfill_profit_records(apps, schema_editor):
	Invoice = apps.get_model("invoices", "Invoice")
	InvoiceItem = apps.get_model("invoices", "InvoiceItem")
	ProfitRecord = apps.get_model("reports", "ProfitRecord")
	Service = apps.get_model("services", "Service")
	Product = apps.get_model("inventory", "Product")

	paid_invoices = Invoice.objects.filter(status="paid")
	for inv in paid_invoices.iterator():
		# Skip if already exists
		if ProfitRecord.objects.filter(invoice_id=inv.id).exists():
			continue

		items = InvoiceItem.objects.filter(invoice_id=inv.id).select_related("product", "service")
		product_sales = Decimal("0.00")
		product_cost = Decimal("0.00")
		product_profit = Decimal("0.00")
		service_sales = Decimal("0.00")
		service_cost = Decimal("0.00")
		service_profit = Decimal("0.00")

		for it in items:
			qty = getattr(it, "quantity", None) or Decimal("0.00")
			if qty <= Decimal("0.00"):
				continue
			unit_price = getattr(it, "unit_price", None) or Decimal("0.00")
			line_sales = (qty * unit_price).quantize(Decimal("0.01"))

			if getattr(it, "product_id", None):
				unit_cost = getattr(it, "unit_cost", None) or Decimal("0.00")
				# Fallback to product cost_price if unit_cost wasn't stored.
				if unit_cost == Decimal("0.00"):
					try:
						prod = Product.objects.get(pk=it.product_id)
						unit_cost = getattr(prod, "cost_price", None) or Decimal("0.00")
					except Exception:
						unit_cost = Decimal("0.00")
				line_cost = (qty * unit_cost).quantize(Decimal("0.01"))
				product_sales += line_sales
				product_cost += line_cost
				product_profit += (line_sales - line_cost)
				continue

			if getattr(it, "service_id", None):
				try:
					svc = Service.objects.get(pk=it.service_id)
					unit_charge = getattr(svc, "service_charge", None) or Decimal("0.00")
				except Exception:
					unit_charge = Decimal("0.00")
				line_cost = (qty * unit_charge).quantize(Decimal("0.01"))
				service_sales += line_sales
				service_cost += line_cost
				service_profit += (line_sales - line_cost)
				continue

		ProfitRecord.objects.create(
			invoice_id=inv.id,
			branch_id=getattr(inv, "branch_id", None),
			currency=getattr(inv, "currency", "UGX") or "UGX",
			product_sales_total=product_sales.quantize(Decimal("0.01")),
			product_cost_total=product_cost.quantize(Decimal("0.01")),
			product_profit_total=product_profit.quantize(Decimal("0.01")),
			service_sales_total=service_sales.quantize(Decimal("0.01")),
			service_cost_total=service_cost.quantize(Decimal("0.01")),
			service_profit_total=service_profit.quantize(Decimal("0.01")),
		)


class Migration(migrations.Migration):
	dependencies = [
		("reports", "0001_initial"),
		("invoices", "0010_invoiceitem_unit_cost"),
		("inventory", "0015_product_cost_price"),
		("services", "0002_servicecategory_service_profit_amount_and_more"),
	]

	operations = [
		migrations.RunPython(backfill_profit_records, migrations.RunPython.noop),
	]
