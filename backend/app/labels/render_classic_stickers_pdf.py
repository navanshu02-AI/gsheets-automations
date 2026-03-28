from __future__ import annotations

from io import BytesIO
import re
from typing import Any, Sequence

import pandas as pd

from .render_labels_pdf import POINTS_PER_INCH

CLASSIC_STICKER_PAGE_SIZES = {
    "2x2": (2 * POINTS_PER_INCH, 2 * POINTS_PER_INCH),
    "4x2": (4 * POINTS_PER_INCH, 2 * POINTS_PER_INCH),
    "4x4": (4 * POINTS_PER_INCH, 4 * POINTS_PER_INCH),
    "4x6": (4 * POINTS_PER_INCH, 6 * POINTS_PER_INCH),
}


def resolve_classic_sticker_page_size(label_size: str) -> tuple[float, float]:
    normalized_size = str(label_size or "").strip().lower()
    if normalized_size not in CLASSIC_STICKER_PAGE_SIZES:
        supported_sizes = ", ".join(CLASSIC_STICKER_PAGE_SIZES)
        raise ValueError(
            f"Unsupported classic sticker label size '{label_size}'. "
            f"Supported sizes: {supported_sizes}"
        )
    return CLASSIC_STICKER_PAGE_SIZES[normalized_size]


def normalize_classic_sticker_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    return normalized


def truncate_classic_sticker_text_to_width(
    pdf: Any, text: str, font_name: str, font_size: float, max_width: float
) -> str:
    if max_width <= 0:
        return ""
    if pdf.stringWidth(text, font_name, font_size) <= max_width:
        return text

    ellipsis = "..."
    ellipsis_width = pdf.stringWidth(ellipsis, font_name, font_size)
    if ellipsis_width >= max_width:
        return ""

    output = text
    while output and pdf.stringWidth(output, font_name, font_size) + ellipsis_width > max_width:
        output = output[:-1]
    return f"{output}{ellipsis}" if output else ""


def fit_classic_sticker_font_size(
    pdf: Any,
    lines: Sequence[dict[str, str]],
    max_width: float,
    max_height: float,
    preferred_size: float,
    minimum_size: float = 6.0,
) -> float:
    if not lines:
        return preferred_size

    size = preferred_size
    while size >= minimum_size - 1e-6:
        line_gap = size * 0.30
        block_height = (len(lines) * size) + (max(0, len(lines) - 1) * line_gap)
        widest_line = max(
            pdf.stringWidth(f"{line['label']} : ", "Helvetica", size)
            + pdf.stringWidth(line["value"], "Helvetica-Bold", size)
            for line in lines
        )
        if widest_line <= max_width and block_height <= max_height:
            return size
        size -= 0.5
    return minimum_size


def _normalize_header(value: object) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _coerce_classic_sticker_field(field: object) -> tuple[str, str] | None:
    if isinstance(field, str):
        key = field.strip()
        return (key, key) if key else None

    if not isinstance(field, dict):
        return None

    if field.get("selected") is False:
        return None

    raw_key = (
        field.get("key")
        or field.get("column")
        or field.get("field")
        or field.get("name")
        or field.get("id")
    )
    key = str(raw_key or "").strip()
    if not key:
        return None

    raw_label = field.get("label") or field.get("display_label") or key
    label = str(raw_label).strip() or key
    return key, label


def extract_classic_sticker_rows(
    frame: pd.DataFrame, selected_fields: Sequence[object]
) -> list[dict[str, list[dict[str, str]]]]:
    if frame is None or frame.empty:
        return []

    resolved_fields: list[tuple[str, str]] = []
    column_lookup = {str(column): str(column) for column in frame.columns}
    normalized_lookup = {
        _normalize_header(column): str(column)
        for column in frame.columns
        if _normalize_header(column)
    }

    for field in selected_fields:
        coerced = _coerce_classic_sticker_field(field)
        if coerced is None:
            continue

        requested_key, label = coerced
        actual_column = column_lookup.get(requested_key)
        if actual_column is None:
            actual_column = normalized_lookup.get(_normalize_header(requested_key))
        if actual_column is None:
            continue

        resolved_fields.append((actual_column, label))

    if not resolved_fields:
        raise ValueError(
            "Selected classic sticker fields do not match any columns in the sheet. "
            f"Available columns: {[str(column) for column in frame.columns]}"
        )

    sticker_rows: list[dict[str, list[dict[str, str]]]] = []
    for _, record in frame.iterrows():
        lines: list[dict[str, str]] = []
        for actual_column, label in resolved_fields:
            value = normalize_classic_sticker_value(record.get(actual_column, ""))
            if not value:
                continue
            lines.append({"label": label, "value": value})

        if lines:
            sticker_rows.append({"lines": lines})

    return sticker_rows


def suggest_classic_sticker_filename(label_size: str) -> str:
    normalized_size = str(label_size or "").strip().lower() or "stickers"
    safe_size = re.sub(r"[^a-z0-9]+", "-", normalized_size).strip("-")
    return f"classic-stickers-{safe_size or 'labels'}.pdf"


def generate_classic_stickers_pdf(
    sticker_rows: list[dict[str, list[dict[str, str]]]],
    label_size: str,
    padding_in: float,
) -> bytes:
    from reportlab.pdfgen import canvas

    if padding_in < 0:
        raise ValueError("padding_in must be greater than or equal to 0 inches")
    if not sticker_rows:
        raise ValueError("No classic sticker rows provided for PDF generation")

    page_width, page_height = resolve_classic_sticker_page_size(label_size)
    padding = padding_in * POINTS_PER_INCH
    if (padding * 2) >= page_width or (padding * 2) >= page_height:
        raise ValueError(f"Padding is too large for {label_size} page size")

    safe_x = padding
    safe_y = padding
    safe_width = page_width - (2 * padding)
    safe_height = page_height - (2 * padding)

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(page_width, page_height))

    for sticker in sticker_rows:
        lines = sticker["lines"]
        preferred_size = min(
            18.0,
            max(8.0, min(safe_width / 10.5, safe_height / max((len(lines) * 1.55), 1.0))),
        )
        font_size = fit_classic_sticker_font_size(
            pdf,
            lines,
            max_width=safe_width,
            max_height=safe_height,
            preferred_size=preferred_size,
        )
        line_gap = font_size * 0.30
        line_step = font_size + line_gap
        block_height = (len(lines) * font_size) + (max(0, len(lines) - 1) * line_gap)
        top_y = safe_y + safe_height - max(0.0, (safe_height - block_height) / 2.0)
        baseline_y = top_y - font_size

        for line_index, line in enumerate(lines):
            label_text = f"{line['label']} : "
            value_text = line["value"]
            max_label_width = safe_width * 0.45
            label_output = truncate_classic_sticker_text_to_width(
                pdf, label_text, "Helvetica", font_size, max_label_width
            )
            label_width = pdf.stringWidth(label_output, "Helvetica", font_size)
            value_max_width = max(0.0, safe_width - label_width)
            value_output = truncate_classic_sticker_text_to_width(
                pdf, value_text, "Helvetica-Bold", font_size, value_max_width
            )

            y = baseline_y - (line_index * line_step)
            pdf.setFont("Helvetica", font_size)
            pdf.drawString(safe_x, y, label_output)
            pdf.setFont("Helvetica-Bold", font_size)
            pdf.drawString(safe_x + label_width, y, value_output)

        pdf.showPage()

    pdf.save()
    return stream.getvalue()
