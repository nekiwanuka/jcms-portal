from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template


register = template.Library()


@register.filter(name="money")
def money(val):
	"""Format numeric values with thousands separators.

	Usage in templates:
		{{ amount|money }}  ->  1,000,000
		{{ amount|money }}  ->  1,000,000.50
	"""
	try:
		if val is None or val == "":
			return "0"

		# Avoid Decimal(float) binary artifacts; parse floats via str().
		dec = val if isinstance(val, Decimal) else Decimal(str(val))
		dec = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		if dec == dec.to_integral_value():
			return f"{dec:,.0f}"
		return f"{dec:,.2f}"
	except (InvalidOperation, ValueError, TypeError):
		return str(val)
