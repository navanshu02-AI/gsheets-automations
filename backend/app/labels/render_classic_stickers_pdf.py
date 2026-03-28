from __future__ import annotations

from io import BytesIO
import json
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
            f"Invalid label size '{label_size}'. Choose one of: {supported_sizes}."
        )
    return CLASSIC_STICKER_PAGE_SIZES[normalized_size]


def validate_classic_sticker_padding(label_size: str, padding_in: float) -> float:
    try:
        numeric_padding = float(padding_in)
    except (TypeError, ValueError) as exc:
        raise ValueError("Padding must be a number in inches.") from exc

    if numeric_padding < 0:
        raise ValueError("Padding must be 0 or greater.")

    page_width, page_height = resolve_classic_sticker_page_size(label_size)
    padding_points = numeric_padding * POINTS_PER_INCH
    if (padding_points * 2) >= page_width or (padding_points * 2) >= page_height:
        raise ValueError(
            f"Padding {numeric_padding:g}in is too large for {label_size} labels. "
            "Reduce the padding and try again."
        )
    return numeric_padding


def parse_classic_sticker_config(config_text: str | None) -> dict[str, object]:
    if config_text is None or not config_text.strip():
        raise ValueError("Classic sticker settings are missing. Send classic_sticker_config.")

    try:
        payload = json.loads(config_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Classic sticker settings are not valid JSON: {exc.msg}.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Classic sticker settings must be a JSON object.")

    raw_sheet_name = str(payload.get("sheet_name") or "")
    if not raw_sheet_name.strip():
        raise ValueError("Choose a sheet for classic stickers.")
    sheet_name = raw_sheet_name

    label_size = str(payload.get("label_size") or "").strip().lower()
    if not label_size:
        raise ValueError("Choose a label size for classic stickers.")
    resolve_classic_sticker_page_size(label_size)

    raw_padding = payload.get("padding_in")
    if raw_padding is None:
        raise ValueError("Enter padding for classic stickers.")
    padding_in = validate_classic_sticker_padding(label_size, raw_padding)

    fields = payload.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("Select at least one field for classic stickers.")

    normalized_fields: list[dict[str, str]] = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise ValueError(
                f"Field {index + 1} must be an object with optional column, label, and value."
            )
        column = str(field.get("column") or "").strip()
        label = str(field.get("label") or "").strip()
        raw_value = field.get("value", field.get("custom_value", ""))
        value = normalize_classic_sticker_value(raw_value)
        if not label:
            label = column or f"Field {index + 1}"

        if normalized_fields and column:
            previous = normalized_fields[-1]
            if previous.get("column", "") == column and previous.get("label", "") == label:
                raise ValueError(
                    f"Field {index + 1} repeats '{column}' with the same label immediately after itself. "
                    "Remove the accidental duplicate or change the label if you want both lines."
                )
        normalized_fields.append({"column": column, "label": label, "value": value})

    return {
        "sheet_name": sheet_name,
        "label_size": label_size,
        "padding_in": padding_in,
        "fields": normalized_fields,
    }


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


def _is_unnamed_header(value: object) -> bool:
    normalized = _normalize_header(value)
    return bool(normalized) and normalized.startswith("unnamed")


def _dedupe_classic_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    deduped: list[str] = []
    for index, header in enumerate(headers):
        candidate = header.strip() if header.strip() else f"unnamed_{index + 1}"
        count = seen.get(candidate, 0) + 1
        seen[candidate] = count
        deduped.append(candidate if count == 1 else f"{candidate}_{count}")
    return deduped


def _prepare_classic_sticker_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    columns = [str(column) for column in frame.columns]
    if not columns or not all(_is_unnamed_header(column) for column in columns):
        return frame, {str(column): str(column) for column in frame.columns}

    first_row = frame.iloc[0] if len(frame.index) > 0 else None
    if first_row is None:
        return frame, {str(column): str(column) for column in frame.columns}

    header_candidates = [normalize_classic_sticker_value(value) for value in first_row.tolist()]
    non_empty_headers = [header for header in header_candidates if header]
    if len(non_empty_headers) < max(1, len(columns) // 2):
        return frame, {str(column): str(column) for column in frame.columns}

    deduped_headers = _dedupe_classic_headers(header_candidates)
    prepared = frame.iloc[1:].copy()
    prepared.columns = deduped_headers
    prepared = prepared.dropna(how="all")

    aliases = {
        _normalize_header(header): actual
        for header, actual in zip(deduped_headers, prepared.columns, strict=False)
        if _normalize_header(header)
    }
    return prepared, aliases


def _coerce_classic_sticker_field(field: object) -> dict[str, str] | None:
    if isinstance(field, str):
        key = field.strip()
        return {"column": key, "label": key, "value": ""} if key else None

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
    raw_label = field.get("label") or field.get("display_label") or key
    label = str(raw_label).strip() or key
    raw_value = field.get("value", field.get("custom_value", ""))
    value = normalize_classic_sticker_value(raw_value)

    if not key and not label:
        return None

    if not label:
        label = key

    return {"column": key, "label": label, "value": value}


def extract_classic_sticker_rows(
    frame: pd.DataFrame, selected_fields: Sequence[object]
) -> list[dict[str, list[dict[str, str]]]]:
    if frame is None or frame.empty:
        return []

    prepared_frame, prepared_aliases = _prepare_classic_sticker_frame(frame)
    resolved_fields: list[dict[str, str]] = []
    column_lookup = {str(column): str(column) for column in prepared_frame.columns}
    normalized_lookup = {
        _normalize_header(column): str(column)
        for column in prepared_frame.columns
        if _normalize_header(column)
    }
    normalized_lookup.update(prepared_aliases)

    for field in selected_fields:
        coerced = _coerce_classic_sticker_field(field)
        if coerced is None:
            continue

        requested_key = coerced.get("column", "").strip()
        label = coerced.get("label", "").strip()
        static_value = coerced.get("value", "")

        if requested_key:
            actual_column = column_lookup.get(requested_key)
            if actual_column is None:
                actual_column = normalized_lookup.get(_normalize_header(requested_key))
            if actual_column is None:
                continue

            resolved_fields.append(
                {
                    "kind": "column",
                    "column": actual_column,
                    "label": label,
                    "value": static_value,
                }
            )
            continue

        if label:
            resolved_fields.append({"kind": "static", "label": label, "value": static_value})

    if not resolved_fields:
        raise ValueError(
            "Selected classic sticker fields do not match any columns in the sheet. "
            f"Available columns: {[str(column) for column in prepared_frame.columns]}"
        )

    sticker_rows: list[dict[str, list[dict[str, str]]]] = []
    for _, record in prepared_frame.iterrows():
        lines: list[dict[str, str]] = []
        for field in resolved_fields:
            label = field["label"]
            if field.get("kind") == "column":
                value = normalize_classic_sticker_value(record.get(field["column"], ""))
                if not value:
                    value = field.get("value", "")
                if not value:
                    continue
                lines.append({"label": label, "value": value})
                continue

            value = field.get("value", "") or "____"
            lines.append({"label": label, "value": value})

        if lines:
            sticker_rows.append({"lines": lines})

    return sticker_rows


def suggest_classic_sticker_filename(filename_hint: str, label_size: str) -> str:
    normalized_size = str(label_size or "").strip().lower() or "labels"
    safe_size = re.sub(r"[^a-z0-9]+", "-", normalized_size).strip("-") or "labels"
    base_name = re.sub(r"\.[^.]+$", "", str(filename_hint or "").strip())
    safe_base = re.sub(r"[^A-Za-z0-9_.-]+", "-", base_name).strip("-.")
    if safe_base:
        return f"{safe_base}-classic-stickers-{safe_size}.pdf"
    return f"classic-stickers-{safe_size}.pdf"


def generate_classic_stickers_pdf(
    sticker_rows: list[dict[str, list[dict[str, str]]]],
    label_size: str,
    padding_in: float,
) -> bytes:
    from reportlab.pdfgen import canvas

    if padding_in < 0:
        raise ValueError("Padding must be 0 or greater.")
    if not sticker_rows:
        raise ValueError("No printable rows found for classic stickers.")

    page_width, page_height = resolve_classic_sticker_page_size(label_size)
    padding = validate_classic_sticker_padding(label_size, padding_in) * POINTS_PER_INCH

    safe_x = padding
    safe_y = padding
    safe_width = page_width - (2 * padding)
    safe_height = page_height - (2 * padding)
    content_inset = min(12.0, max(4.0, min(safe_width, safe_height) * 0.06))

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(page_width, page_height))

    for sticker in sticker_rows:
        lines = sticker["lines"]
        pdf.setLineWidth(1.0)
        pdf.rect(safe_x, safe_y, safe_width, safe_height, stroke=1, fill=0)
        content_x = safe_x + content_inset
        content_y = safe_y + content_inset
        content_width = max(1.0, safe_width - (2 * content_inset))
        content_height = max(1.0, safe_height - (2 * content_inset))

        preferred_size = min(
            18.0,
            max(8.0, min(content_width / 10.5, content_height / max((len(lines) * 1.55), 1.0))),
        )
        font_size = fit_classic_sticker_font_size(
            pdf,
            lines,
            max_width=content_width,
            max_height=content_height,
            preferred_size=preferred_size,
        )
        line_gap = font_size * 0.30
        line_step = font_size + line_gap
        block_height = (len(lines) * font_size) + (max(0, len(lines) - 1) * line_gap)
        top_y = content_y + content_height - max(0.0, (content_height - block_height) / 2.0)
        baseline_y = top_y - font_size

        for line_index, line in enumerate(lines):
            label_text = f"{line['label']} : "
            value_text = line["value"]
            full_label_width = pdf.stringWidth(label_text, "Helvetica", font_size)
            full_value_width = pdf.stringWidth(value_text, "Helvetica-Bold", font_size)

            if full_label_width + full_value_width <= content_width:
                label_output = label_text
                value_output = value_text
            else:
                target_label_width = min(full_label_width, content_width * 0.60)
                target_value_width = max(0.0, content_width - target_label_width)

                if full_value_width > target_value_width:
                    target_value_width = min(full_value_width, content_width * 0.65)
                    target_label_width = max(0.0, content_width - target_value_width)

                label_output = truncate_classic_sticker_text_to_width(
                    pdf, label_text, "Helvetica", font_size, target_label_width
                )
                label_width = pdf.stringWidth(label_output, "Helvetica", font_size)
                value_output = truncate_classic_sticker_text_to_width(
                    pdf,
                    value_text,
                    "Helvetica-Bold",
                    font_size,
                    max(0.0, content_width - label_width),
                )

            label_width = pdf.stringWidth(label_output, "Helvetica", font_size)

            y = baseline_y - (line_index * line_step)
            pdf.setFont("Helvetica", font_size)
            pdf.drawString(content_x, y, label_output)
            pdf.setFont("Helvetica-Bold", font_size)
            pdf.drawString(content_x + label_width, y, value_output)

        pdf.showPage()

    pdf.save()
    return stream.getvalue()
