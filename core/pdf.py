from __future__ import annotations

import shutil
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Iterable

from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Frame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def money(val) -> str:
	"""Format monetary amounts consistently across PDFs/exports."""
	try:
		from core.templatetags.formatting import money as money_filter
		return money_filter(val)
	except Exception:
		return str(val)


_COMPANY_FOOTER_LINE_1 = (
	"JAMBAS IMAGING (U) LTD - Integrated solutions in printing, branding, IT Products, "
	"IT support services, safety gears, medical supplies, and stationery."
)
_COMPANY_FOOTER_LINE_2 = "+256 200 902 849  |   info@jambasimaging.com  |   F-26, Nasser Road Mall, Kampala – Uganda"


def branding_static_paths() -> tuple[str | None, str | None]:
	"""Return (svg_logo_path, png_logo_path) if available via staticfiles finders."""
	try:
		from django.contrib.staticfiles import finders

		svg_path = finders.find("images/jambas-logo-white.svg")
		png_path = finders.find("images/jambas-company-logo.png")
		return svg_path, png_path
	except Exception:
		return None, None


def draw_header_footer(canvas, doc, *, title: str) -> None:
	"""Draw a branded header/footer on each PDF page."""
	page_width, page_height = doc.pagesize
	left = doc.leftMargin
	right = page_width - doc.rightMargin

	# Responsive sizing for A4 vs A5 pages.
	bar_h = 62 if page_height >= 750 else 48
	title_font = 13 if page_height >= 750 else 11
	logo_h = 34 if page_height >= 750 else 26
	logo_w = 210 if page_height >= 750 else 160
	footer_line_y = 58 if page_height >= 750 else 44
	canvas.saveState()

	# Header bar (blue) + white logo
	canvas.setFillColor(colors.HexColor("#0d6efd"))
	canvas.rect(0, page_height - bar_h, page_width, bar_h, fill=1, stroke=0)

	svg_path, png_path = branding_static_paths()
	logo_drawn = False
	logo_x = left
	logo_y = page_height - bar_h + (14 if page_height >= 750 else 12)
	if svg_path:
		try:
			from svglib.svglib import svg2rlg
			from reportlab.graphics import renderPDF

			drawing = svg2rlg(svg_path)
			if drawing and getattr(drawing, "width", 0) and getattr(drawing, "height", 0):
				scale = min(logo_w / float(drawing.width), logo_h / float(drawing.height))
				drawing.scale(scale, scale)
				renderPDF.draw(drawing, canvas, logo_x, logo_y)
				logo_drawn = True
		except Exception:
			logo_drawn = False
	if (not logo_drawn) and png_path:
		try:
			canvas.drawImage(png_path, logo_x, logo_y, width=logo_h, height=logo_h, mask="auto")
			logo_drawn = True
		except Exception:
			pass

	# Document title on the right
	canvas.setFillColor(colors.white)
	canvas.setFont("Helvetica-Bold", title_font)
	canvas.drawRightString(right, page_height - (24 if page_height >= 750 else 22), title)

	# Footer
	canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
	canvas.setLineWidth(0.6)
	canvas.line(left, footer_line_y, right, footer_line_y)

	footer_style = ParagraphStyle(
		"pdf_footer",
		fontName="Helvetica",
		fontSize=(8 if page_height >= 750 else 7),
		leading=(9 if page_height >= 750 else 8),
		textColor=colors.HexColor("#334155"),
		alignment=1,
	)
	footer_bottom = 12 if page_height >= 750 else 10
	footer_frame_h = max(22, footer_line_y - footer_bottom - 6)
	footer_frame = Frame(
		left,
		footer_bottom,
		right - left,
		footer_frame_h,
		leftPadding=0,
		rightPadding=0,
		topPadding=0,
		bottomPadding=0,
		showBoundary=0,
	)
	footer_frame.addFromList(
		[
			Paragraph(_COMPANY_FOOTER_LINE_1, footer_style),
			Paragraph(_COMPANY_FOOTER_LINE_2, footer_style),
		],
		canvas,
	)

	canvas.restoreState()


def kv_table(*, styles, left_rows: list[tuple[str, str]], right_rows: list[tuple[str, str]]):
	"""Two-column key/value table for PDFs."""
	label_style = ParagraphStyle(
		"pdf_kv_label",
		parent=styles["Normal"],
		fontSize=8.5,
		leading=10,
		textColor=colors.HexColor("#475569"),
	)
	value_style = ParagraphStyle(
		"pdf_kv_value",
		parent=styles["Normal"],
		fontSize=10,
		leading=12,
		textColor=colors.HexColor("#0f172a"),
	)

	max_rows = max(len(left_rows), len(right_rows))
	rows = []
	for i in range(max_rows):
		lk, lv = left_rows[i] if i < len(left_rows) else ("", "")
		rk, rv = right_rows[i] if i < len(right_rows) else ("", "")
		rows.append(
			[
				Paragraph(f"<b>{lk}</b><br/>{lv}", value_style) if lk else "",
				Paragraph(f"<b>{rk}</b><br/>{rv}", value_style) if rk else "",
			]
		)

	table = Table(rows, colWidths=["50%", "50%"])
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
				("VALIGN", (0, 0), (-1, -1), "TOP"),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
			]
		)
	)
	return table


def pdf_response(title: str, header: list[str], rows: list[list[str]], filename: str, *, inline: bool = False) -> HttpResponse:
	"""Generate a simple, reliable PDF table export."""
	buffer = BytesIO()
	doc = SimpleDocTemplate(
		buffer,
		pagesize=A4,
		title=title,
		topMargin=90,
		bottomMargin=72,
		leftMargin=36,
		rightMargin=36,
	)
	styles = getSampleStyleSheet()
	styles.add(
		ParagraphStyle(
			"pdf_export_hint",
			parent=styles["Normal"],
			fontSize=9,
			leading=11,
			textColor=colors.HexColor("#475569"),
		)
	)

	elements = [
		Paragraph(title, styles["Title"]),
		Spacer(1, 6),
		Paragraph("Generated export", styles["pdf_export_hint"]),
		Spacer(1, 10),
	]

	def _cell_text(value) -> str:
		if value is None:
			return ""
		return str(value)

	def _looks_numeric(text: str) -> bool:
		t = (text or "").strip()
		if not t:
			return False
		t = t.replace(",", "")
		parts = t.split()
		if len(parts) == 2 and all(ch.isalpha() for ch in parts[0]):
			t = parts[1]
		try:
			float(t)
			return True
		except Exception:
			return False

	sample_rows = rows[:200] if rows else []
	col_count = len(header)
	max_lens = [len(_cell_text(h)) for h in header]
	for r in sample_rows:
		for idx in range(min(col_count, len(r))):
			max_lens[idx] = max(max_lens[idx], len(_cell_text(r[idx])))

	wide_headers = {"description", "details", "name", "client", "title"}
	weights: list[float] = []
	for idx, h in enumerate(header):
		base = min(max_lens[idx], 42)
		if (h or "").strip().lower() in wide_headers:
			base *= 1.4
		weights.append(max(8.0, float(base)))
	wsum = sum(weights) or 1.0
	col_widths = [(w / wsum) * float(doc.width) for w in weights]

	numeric_headers = {
		"amount",
		"total",
		"unit price",
		"price",
		"value",
		"vat",
		"profit",
		"revenue",
		"balance",
		"stock",
		"reorder level",
	}
	numeric_cols: set[int] = set()
	for idx, h in enumerate(header):
		hn = (h or "").strip().lower()
		if hn in numeric_headers:
			numeric_cols.add(idx)
			continue
		num_like = 0
		seen = 0
		for r in sample_rows:
			if idx >= len(r):
				continue
			seen += 1
			if _looks_numeric(_cell_text(r[idx])):
				num_like += 1
		if seen >= 5 and (num_like / max(seen, 1)) >= 0.8:
			numeric_cols.add(idx)

	data = [header] + rows
	table = Table(data, repeatRows=1, colWidths=col_widths)
	table.setStyle(
		TableStyle(
			[
				("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
				("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
				("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
				("FONTSIZE", (0, 0), (-1, 0), 10),
				("ALIGN", (0, 0), (-1, 0), "LEFT"),
				("LEFTPADDING", (0, 0), (-1, -1), 6),
				("RIGHTPADDING", (0, 0), (-1, -1), 6),
				("TOPPADDING", (0, 0), (-1, -1), 4),
				("BOTTOMPADDING", (0, 0), (-1, -1), 4),
				("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
				("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
				("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
			]
		)
	)
	for idx in sorted(numeric_cols):
		table.setStyle(TableStyle([("ALIGN", (idx, 1), (idx, -1), "RIGHT")]))

	elements.append(table)
	doc.build(
		elements,
		onFirstPage=lambda c, d: draw_header_footer(c, d, title=title),
		onLaterPages=lambda c, d: draw_header_footer(c, d, title=title),
	)

	pdf_bytes = buffer.getvalue()
	buffer.close()

	response = HttpResponse(pdf_bytes, content_type="application/pdf")
	disposition = "inline" if inline else "attachment"
	response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
	return response
