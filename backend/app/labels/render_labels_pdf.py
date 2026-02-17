from __future__ import annotations

from collections import OrderedDict
from io import BytesIO
import re
from typing import Any

import pandas as pd

POINTS_PER_INCH = 72.0
LANDSCAPE_4X6 = (6 * POINTS_PER_INCH, 4 * POINTS_PER_INCH)
PORTRAIT_4X6 = (4 * POINTS_PER_INCH, 6 * POINTS_PER_INCH)

REQUIRED_KEYS = {"po", "invoice", "carton", "article_code", "size", "qty"}
COLUMN_ALIASES = {
    "po": {
        "po",
        "po#",
        "po no",
        "po_no",
        "po number",
        "po_number",
        "purchase order",
        "po_number",
    },
    "invoice": {
        "invoice",
        "invoice#",
        "invoice no",
        "invoice_no",
        "invoice number",
        "invoice_number",
        "invoice_number",
    },
    "carton": {
        "carton",
        "carton#",
        "carton #",
        "carton no",
        "carton_no",
        "cartonno",
        "cartonno#",
        "cartonno #",
        "carton number",
        "carton_number",
        "carton count",
        "carton_count",
        "carton_count",
    },
    "ean_code": {"ean", "ean code", "ean_code"},
    "article_code": {"article code", "article_code", "articlecode", "sku"},
    "size": {"size"},
    "qty": {"qty", "quantity", "packed qty", "packed_qty", "order qty", "order_qty"},
}


def _to_string(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalize_header(value: object) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _to_canonical_key(header: object) -> str | None:
    normalized = _normalize_header(header)
    if not normalized:
        return None
    compact = normalized.replace(" ", "")
    for key, aliases in COLUMN_ALIASES.items():
        alias_compact = {alias.replace(" ", "") for alias in aliases}
        if normalized in aliases or compact in alias_compact:
            return key
    return None


def _parse_po_from_filename(filename_hint: str) -> str:
    if not filename_hint.strip():
        return ""
    match = re.search(r"po#?\s*([a-z0-9-]+)", filename_hint, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _normalize_qty(value: object) -> tuple[str, float]:
    text = _to_string(value)
    if not text:
        return "", 0.0
    numeric = pd.to_numeric([text], errors="coerce")[0]
    if pd.isna(numeric):
        return "", 0.0
    numeric_value = float(numeric)
    if numeric_value <= 0:
        return "", numeric_value
    if numeric_value.is_integer():
        return str(int(numeric_value)), numeric_value
    return str(numeric_value), numeric_value


def extract_label_rows(
    sheets: dict[str, pd.DataFrame],
    filename_hint: str = "",
    invoice_override: str = "",
    po_override: str = "",
    preferred_sheet: str = "",
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    detected_columns: dict[str, list[str]] = {}
    parsed_po_from_filename = _parse_po_from_filename(filename_hint)

    if preferred_sheet and preferred_sheet in sheets:
        ordered_sheet_names = [preferred_sheet]
    else:
        delivery_sheet_names = [
            sheet_name for sheet_name in sheets.keys() if sheet_name.endswith("__delivery_print")
        ]
        ordered_sheet_names = delivery_sheet_names or list(sheets.keys())

    for sheet_name in ordered_sheet_names:
        frame = sheets[sheet_name]
        if frame is None or frame.empty:
            continue

        mapping: dict[str, str] = {}
        for column in frame.columns:
            canonical = _to_canonical_key(column)
            if canonical is None:
                continue
            actual_column = str(column)
            if canonical in mapping.values():
                continue
            mapping[actual_column] = canonical

        normalized = frame.rename(columns=mapping)
        detected_columns[sheet_name] = [str(column) for column in frame.columns]
        has_article = "article_code" in normalized.columns
        has_size = "size" in normalized.columns
        has_qty = "qty" in normalized.columns

        if not (has_article and has_size and has_qty):
            continue

        metadata = frame.attrs.get("sheet_metadata", {})
        sheet_po = _to_string(metadata.get("po_number", ""))
        sheet_invoice = _to_string(metadata.get("invoice_number", ""))
        override_invoice = invoice_override.strip()
        override_po = po_override.strip()

        for _, record in normalized.iterrows():
            article_code = _to_string(record.get("article_code", ""))
            ean_code = _to_string(record.get("ean_code", ""))
            size = _to_string(record.get("size", ""))
            qty, qty_numeric = _normalize_qty(record.get("qty", ""))
            if not article_code or not size or qty_numeric <= 0:
                continue

            po_value = (
                override_po
                or _to_string(record.get("po", ""))
                or sheet_po
                or parsed_po_from_filename
            )
            invoice_value = (
                override_invoice
                or _to_string(record.get("invoice", ""))
                or sheet_invoice
            )
            carton_value = _to_string(record.get("carton", "")) or "1"

            rows.append(
                {
                    "po": po_value,
                    "invoice": invoice_value,
                    "carton": carton_value,
                    "ean_code": ean_code,
                    "article_code": article_code,
                    "size": size,
                    "qty": qty,
                }
            )

    if not rows:
        if preferred_sheet and preferred_sheet in detected_columns:
            raise ValueError(
                "Selected delivery sheet could not be used for labels. "
                "Expected columns mapping to Article Code, Size, and Qty. "
                f"Detected columns: {detected_columns[preferred_sheet]}"
            )
        first_sheet = next(iter(detected_columns), "")
        if first_sheet:
            raise ValueError(
                f"Sheet '{first_sheet}' is missing required columns for labels. "
                "Expected columns mapping to Article Code, Size, and Qty. "
                f"Detected columns: {detected_columns[first_sheet]}"
            )
        raise ValueError("No valid label rows found in uploaded file")
    return rows


def _group_rows(rows: list[dict[str, str]]) -> OrderedDict[tuple[str, str, str], list[dict[str, str]]]:
    grouped: OrderedDict[tuple[str, str, str], list[dict[str, str]]] = OrderedDict()
    for row in rows:
        key = (row["po"], row["invoice"], row["carton"])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(row)
    return grouped


def suggest_download_filename(rows: list[dict[str, str]]) -> str:
    unique_pos = {row["po"] for row in rows if row["po"].strip()}
    if len(unique_pos) == 1:
        po = next(iter(unique_pos))
        safe_po = re.sub(r"[^A-Za-z0-9_.-]+", "-", po).strip("-")
        if safe_po:
            return f"PO# {safe_po}.pdf"
    return "PO# labels.pdf"


def _fit_metrics(table_height: float, row_count: int) -> tuple[float, float, float]:
    preferred_font = 16.0
    preferred_line_factor = 1.20
    header_height_factor = 1.16
    hard_min_font = 8.0
    preferred_min_font = 10.0

    probe = preferred_font
    while probe >= hard_min_font - 1e-6:
        row_height = probe * preferred_line_factor
        header_height = row_height * header_height_factor
        total = header_height + (row_height * row_count)
        if total <= table_height:
            return probe, row_height, header_height
        probe -= 0.5

    denominator = row_count + header_height_factor
    row_height = table_height / denominator if denominator > 0 else table_height
    header_height = row_height * header_height_factor
    font_size = max(hard_min_font, min(preferred_min_font, row_height / preferred_line_factor))
    return font_size, row_height, header_height


def _draw_label_value_line(
    pdf: Any, x: float, y: float, label: str, value: str, font_size: float
) -> None:
    pdf.setFont("Helvetica", font_size)
    pdf.drawString(x, y, label)
    label_width = pdf.stringWidth(label, "Helvetica", font_size)
    pdf.setFont("Helvetica-Bold", font_size)
    pdf.drawString(x + label_width, y, value)


def _fit_label_value_font(
    pdf: Any,
    label: str,
    value: str,
    max_width: float,
    preferred: float,
    minimum: float = 10.0,
) -> float:
    size = preferred
    while size >= minimum:
        width = pdf.stringWidth(label, "Helvetica", size) + pdf.stringWidth(
            value, "Helvetica-Bold", size
        )
        if width <= max_width:
            return size
        size -= 0.5
    return minimum


def generate_labels_pdf(rows: list[dict[str, str]], portrait: bool, padding_in: float) -> bytes:
    from reportlab.pdfgen import canvas

    if padding_in < 0.1 or padding_in > 0.4:
        raise ValueError("padding_in must be between 0.1 and 0.4 inches")

    if not rows:
        raise ValueError("No rows provided for label generation")

    page_width, page_height = PORTRAIT_4X6 if portrait else LANDSCAPE_4X6
    padding = padding_in * POINTS_PER_INCH

    if (padding * 2) >= page_width or (padding * 2) >= page_height:
        raise ValueError("Padding is too large for 4x6 page size")

    safe_x = padding
    safe_y = padding
    safe_width = page_width - (2 * padding)
    safe_height = page_height - (2 * padding)

    header_height = safe_height * 0.35
    header_gap = 0.12 * POINTS_PER_INCH
    table_height = safe_height - header_height - header_gap
    if table_height <= 0:
        raise ValueError("Not enough space to render table with selected padding")

    grouped = _group_rows(rows)
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(page_width, page_height))

    for (po_number, invoice_number, carton_no), group_rows in grouped.items():
        header_top = safe_y + safe_height
        right_block_left = safe_x + (safe_width * (0.64 if portrait else 0.70))
        right_block_right = safe_x + safe_width
        right_center = (right_block_left + right_block_right) / 2.0
        left_block_max_width = (right_block_left - safe_x) - (0.08 * POINTS_PER_INCH)
        header_bottom = safe_y + table_height + header_gap

        preferred_line_font = 14.0 if portrait else 16.0
        po_font = _fit_label_value_font(
            pdf, "PO# ", po_number, left_block_max_width, preferred_line_font
        )
        invoice_font = _fit_label_value_font(
            pdf,
            "Invoice# ",
            invoice_number,
            left_block_max_width,
            preferred_line_font,
        )
        carton_label_font = 18.0 if portrait else 16.0
        carton_value_font = 30.0 if portrait else 28.0

        po_y = header_top - (0.10 * POINTS_PER_INCH) - po_font
        invoice_y = po_y - (0.26 * POINTS_PER_INCH)

        _draw_label_value_line(pdf, safe_x, po_y, "PO# ", po_number, po_font)
        _draw_label_value_line(pdf, safe_x, invoice_y, "Invoice# ", invoice_number, invoice_font)

        pdf.setFont("Helvetica", carton_label_font)
        carton_label_y = po_y
        pdf.drawRightString(right_block_right, carton_label_y, "Carton No.")
        pdf.setFont("Helvetica-Bold", carton_value_font)
        carton_value_y = carton_label_y - (carton_value_font * 0.95)
        min_value_y = header_bottom + (0.04 * POINTS_PER_INCH)
        if carton_value_y < min_value_y:
            carton_value_y = min_value_y
        pdf.drawCentredString(right_center, carton_value_y, carton_no)

        table_top = safe_y + table_height
        column_widths = [safe_width * 0.30, safe_width * 0.35, safe_width * 0.18, safe_width * 0.17]
        x_edges = [
            safe_x,
            safe_x + column_widths[0],
            safe_x + column_widths[0] + column_widths[1],
            safe_x + column_widths[0] + column_widths[1] + column_widths[2],
            safe_x + safe_width,
        ]

        row_font, row_height, header_row_height = _fit_metrics(table_height, len(group_rows))
        header_font = min(18.0, max(row_font + 1.0, 10.0))
        text_pad = 0.07 * POINTS_PER_INCH

        table_bottom = table_top - (header_row_height + (row_height * len(group_rows)))
        table_bottom = max(table_bottom, safe_y)

        pdf.setLineWidth(1.0)
        pdf.rect(safe_x, table_bottom, safe_width, table_top - table_bottom, stroke=1, fill=0)
        for x in x_edges[1:-1]:
            pdf.line(x, table_bottom, x, table_top)

        table_header_bottom = table_top - header_row_height
        pdf.line(safe_x, table_header_bottom, safe_x + safe_width, table_header_bottom)
        for index in range(len(group_rows) - 1):
            y = table_header_bottom - ((index + 1) * row_height)
            pdf.line(safe_x, y, safe_x + safe_width, y)

        header_baseline = table_top - ((header_row_height + header_font) / 2.0) + (header_font * 0.22)
        pdf.setFont("Helvetica-Bold", header_font)
        for idx, header in enumerate(("EAN Code", "Article Code", "Size", "Qty")):
            pdf.drawString(x_edges[idx] + text_pad, header_baseline, header)

        pdf.setFont("Helvetica", row_font)
        for row_index, row in enumerate(group_rows):
            top = table_header_bottom - (row_index * row_height)
            baseline = top - ((row_height + row_font) / 2.0) + (row_font * 0.22)
            values = (row.get("ean_code", ""), row["article_code"], row["size"], row["qty"])
            for col_index, value in enumerate(values):
                pdf.drawString(x_edges[col_index] + text_pad, baseline, value)

        pdf.showPage()

    pdf.save()
    return stream.getvalue()
