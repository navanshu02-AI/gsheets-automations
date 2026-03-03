from __future__ import annotations

from io import BytesIO, StringIO
import re
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field, model_validator


class JoinKeyMapping(BaseModel):
    base_column: str
    source_column: str


class ConcatPartConfig(BaseModel):
    sheet: str
    column: str
    join_keys: list[JoinKeyMapping] = Field(default_factory=list)


class ConcatOperationConfig(BaseModel):
    output_column: str
    delimiter: str = ""
    parts: list[ConcatPartConfig]


class VLookupOperationConfig(BaseModel):
    # Preferred Excel-style fields.
    lookup_value_column: str | None = None
    table_array_sheet: str | None = None
    table_array_lookup_column: str | None = None
    col_index_num: int | None = None
    # `None` means omitted; we treat it as approximate mode (Excel default).
    range_lookup: bool | None = None
    output_column: str | None = None
    advanced_multi_key: bool = False

    # Legacy fields (backward compatibility).
    lookup_mode: Literal["exact", "nearest"] | None = None
    base_key_columns: list[str] = Field(default_factory=list)
    lookup_sheet: str | None = None
    lookup_key_columns: list[str] = Field(default_factory=list)
    return_columns: list[str] = Field(default_factory=list)
    output_prefix: str = ""


class TransformConfig(BaseModel):
    base_sheet: str
    concat_operations: list[ConcatOperationConfig] = Field(default_factory=list)
    vlookup_operations: list[VLookupOperationConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operations(self) -> "TransformConfig":
        if not self.concat_operations and not self.vlookup_operations:
            raise ValueError(
                "At least one concat or vlookup operation is required when config is provided"
            )
        return self


HEADER_SCAN_ROWS = 15
HEADER_REQUIRED_COLUMNS = {"Article Code", "Size"}
HEADER_PREFERRED_COLUMNS = {"EAN", "Order Qty", "Packed Qty", "Carton Count", "Carton"}
COLUMN_ALIASES = {
    "Article Code": {"article code", "article_code"},
    "Size": {"size"},
    "EAN": {"ean", "ean code", "ean_code"},
    "Order Qty": {"order qty", "order_qty", "quantity", "order quantity"},
    "Packed Qty": {"packed qty", "packed_qty", "packed quantity"},
    "Carton Count": {
        "carton",
        "carton#",
        "carton #",
        "carton count",
        "carton_count",
        "carton no",
        "carton no#",
        "carton no #",
        "carton number",
        "cartonnumber",
        "cartonnumber#",
        "cartonnumber #",
    },
}


def _normalize_column_token(value: object) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _canonicalize_column_name(value: object) -> str:
    token = _normalize_column_token(value)
    if not token:
        return ""
    for canonical, aliases in COLUMN_ALIASES.items():
        if token == _normalize_column_token(canonical) or token in aliases:
            return canonical
    return str(value).strip()


def _detect_header_row(raw_frame: pd.DataFrame) -> int | None:
    row_limit = min(len(raw_frame), HEADER_SCAN_ROWS)
    best_row: int | None = None
    best_score = -1
    for row_index in range(row_limit):
        row = raw_frame.iloc[row_index].tolist()
        canonical_headers = {
            _canonicalize_column_name(cell)
            for cell in row
            if str(cell or "").strip()
        }
        if not HEADER_REQUIRED_COLUMNS.issubset(canonical_headers):
            continue
        preferred_score = len(canonical_headers.intersection(HEADER_PREFERRED_COLUMNS))
        if preferred_score > best_score:
            best_score = preferred_score
            best_row = row_index
    return best_row


def _dedupe_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    deduped: list[str] = []
    for index, header in enumerate(headers):
        candidate = header.strip() if header.strip() else f"unnamed_{index + 1}"
        count = seen.get(candidate, 0) + 1
        seen[candidate] = count
        deduped.append(candidate if count == 1 else f"{candidate}_{count}")
    return deduped


def _extract_sheet_metadata(raw_frame: pd.DataFrame, header_row_index: int | None) -> dict[str, str]:
    row_limit = header_row_index if header_row_index is not None else min(len(raw_frame), 5)
    row_limit = max(0, min(row_limit, len(raw_frame)))
    text_rows: list[str] = []
    for row_index in range(row_limit):
        row_values = [str(cell).strip() for cell in raw_frame.iloc[row_index].tolist() if str(cell).strip()]
        if row_values:
            text_rows.append(" ".join(row_values))
    joined_text = " ".join(text_rows)

    po_match = re.search(r"PO#?\s*[:\-]?\s*([A-Za-z0-9\-]+)", joined_text, flags=re.IGNORECASE)
    invoice_match = re.search(
        r"Invoice#?\s*[:\-]?\s*([A-Za-z0-9/\-]+)", joined_text, flags=re.IGNORECASE
    )

    return {
        "po_number": po_match.group(1).strip() if po_match else "",
        "invoice_number": invoice_match.group(1).strip() if invoice_match else "",
    }


def _parse_sheet_with_header_detection(
    raw_frame: pd.DataFrame, fallback_frame: pd.DataFrame
) -> pd.DataFrame:
    header_row_index = _detect_header_row(raw_frame)
    metadata = _extract_sheet_metadata(raw_frame, header_row_index)
    if header_row_index is None:
        frame = fallback_frame.copy()
        frame.attrs["sheet_metadata"] = metadata
        return frame

    raw_headers = raw_frame.iloc[header_row_index].tolist()
    normalized_headers = [_canonicalize_column_name(value) for value in raw_headers]
    deduped_headers = _dedupe_headers(normalized_headers)

    trimmed = raw_frame.iloc[header_row_index + 1 :].copy()
    trimmed.columns = deduped_headers
    trimmed = trimmed.dropna(how="all")
    trimmed.attrs["sheet_metadata"] = metadata
    return trimmed


def _resolve_column_name(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized_to_actual = {
        _normalize_column_token(column): str(column) for column in frame.columns
    }
    for candidate in candidates:
        token = _normalize_column_token(candidate)
        if token in normalized_to_actual:
            return normalized_to_actual[token]
    return None


def _as_text_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if float(value).is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def build_delivery_print_sheet(sheet_df: pd.DataFrame) -> pd.DataFrame | None:
    article_column = _resolve_column_name(sheet_df, ["Article Code", "article_code"])
    size_column = _resolve_column_name(sheet_df, ["Size", "size"])
    packed_qty_column = _resolve_column_name(sheet_df, ["Packed Qty", "packed_qty"])
    order_qty_column = _resolve_column_name(sheet_df, ["Order Qty", "order_qty", "quantity"])
    po_column = _resolve_column_name(
        sheet_df,
        ["PO", "PO#", "po", "po#", "po_number", "po no", "purchase order"],
    )
    invoice_column = _resolve_column_name(
        sheet_df,
        [
            "Invoice",
            "Invoice#",
            "invoice",
            "invoice#",
            "invoice_number",
            "invoice no",
        ],
    )
    ean_column = _resolve_column_name(sheet_df, ["EAN", "ean", "ean_code"])
    carton_column = _resolve_column_name(
        sheet_df,
        [
            "Carton",
            "carton",
            "Carton#",
            "Carton #",
            "carton#",
            "carton #",
            "Carton Count",
            "carton_count",
        ],
    )

    if not article_column:
        return None
    if not packed_qty_column and not order_qty_column:
        return None

    metadata = sheet_df.attrs.get("sheet_metadata", {})
    po_number = _as_text_value(metadata.get("po_number", ""))
    invoice_number = _as_text_value(metadata.get("invoice_number", ""))
    po_source = (
        sheet_df[po_column].map(_as_text_value) if po_column else pd.Series([""] * len(sheet_df))
    )
    invoice_source = (
        sheet_df[invoice_column].map(_as_text_value)
        if invoice_column
        else pd.Series([""] * len(sheet_df))
    )
    if po_number:
        po_source = po_source.replace("", po_number)
    if invoice_number:
        invoice_source = invoice_source.replace("", invoice_number)

    if packed_qty_column:
        packed_series = sheet_df[packed_qty_column]
        if order_qty_column:
            order_series = sheet_df[order_qty_column]
            packed_as_text = packed_series.astype("string").str.strip().replace("<NA>", "")
            qty_source = packed_series.where(packed_as_text != "", other=order_series)
        else:
            qty_source = packed_series
    else:
        qty_source = sheet_df[order_qty_column]  # type: ignore[index]

    qty_numeric = pd.to_numeric(qty_source, errors="coerce").fillna(0)
    carton_source = (
        sheet_df[carton_column].map(_as_text_value) if carton_column else pd.Series(["1"] * len(sheet_df))
    )

    delivery_frame = pd.DataFrame(
        {
            "po_number": po_source,
            "invoice_number": invoice_source,
            "carton_count": carton_source.replace("", "1"),
            "ean_code": sheet_df[ean_column].map(_as_text_value) if ean_column else "",
            "article_code": sheet_df[article_column].map(_as_text_value),
            "size": sheet_df[size_column].map(_as_text_value) if size_column else "",
            "qty": qty_numeric,
        }
    )

    delivery_frame = delivery_frame[
        delivery_frame["article_code"].str.strip().ne("")
        & (delivery_frame["qty"] > 0)
    ].copy()

    if delivery_frame.empty:
        return delivery_frame

    def format_qty(value: object) -> object:
        numeric_value = float(value)
        if numeric_value.is_integer():
            return int(numeric_value)
        return numeric_value

    delivery_frame["qty"] = delivery_frame["qty"].map(format_qty)
    delivery_frame["carton_count_sort"] = pd.to_numeric(
        delivery_frame["carton_count"], errors="coerce"
    ).fillna(1)
    delivery_frame = delivery_frame.sort_values(
        by=["carton_count_sort"], kind="mergesort"
    ).drop(columns=["carton_count_sort"])

    return delivery_frame.reset_index(drop=True)


def _delivery_sheet_name(sheet_name: str, existing_names: set[str]) -> str:
    candidate = f"{sheet_name}__delivery_print"
    if candidate not in existing_names:
        return candidate
    index = 2
    while f"{candidate}_{index}" in existing_names:
        index += 1
    return f"{candidate}_{index}"


def apply_default_automation(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply a simple starter automation for spreadsheet workflows."""
    frame = frame.copy()

    normalized_columns = {
        column: column.strip().lower().replace(" ", "_") for column in frame.columns
    }
    frame = frame.rename(columns=normalized_columns)

    if {"quantity", "unit_price"}.issubset(frame.columns):
        frame["line_total"] = frame["quantity"] * frame["unit_price"]

    if "product" in frame.columns and "is_gusset" not in frame.columns:
        frame["is_gusset"] = frame["product"].astype(str).str.contains(
            "gusset", case=False, na=False
        )

    return frame


def parse_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(StringIO(file_bytes.decode("utf-8-sig")))


def parse_excel_bytes(file_bytes: bytes) -> dict[str, pd.DataFrame]:
    normal_sheets = pd.read_excel(BytesIO(file_bytes), sheet_name=None)
    raw_sheets = pd.read_excel(BytesIO(file_bytes), sheet_name=None, header=None, dtype=object)

    parsed_sheets: dict[str, pd.DataFrame] = {}
    for sheet_name, normal_frame in normal_sheets.items():
        name = str(sheet_name)
        raw_frame = raw_sheets.get(sheet_name)
        if raw_frame is None:
            parsed_sheets[name] = normal_frame
            continue
        parsed_sheets[name] = _parse_sheet_with_header_detection(raw_frame, normal_frame)
    return parsed_sheets


def run_automation_on_sheets(sheets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    automated_sheets = {
        sheet_name: apply_default_automation(frame)
        for sheet_name, frame in sheets.items()
    }

    used_names = set(automated_sheets.keys())
    for sheet_name, frame in sheets.items():
        delivery_frame = build_delivery_print_sheet(frame)
        if delivery_frame is None:
            continue
        delivery_name = _delivery_sheet_name(sheet_name, used_names)
        used_names.add(delivery_name)
        automated_sheets[delivery_name] = delivery_frame

    return automated_sheets


def _require_sheet(all_sheets: dict[str, pd.DataFrame], sheet_name: str) -> pd.DataFrame:
    if sheet_name not in all_sheets:
        raise ValueError(f"Unknown sheet '{sheet_name}'")
    return all_sheets[sheet_name]


def _require_columns(frame: pd.DataFrame, columns: list[str], context: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Unknown column(s) {missing} in {context}")


def _unique_column_name(column_name: str, existing: list[str]) -> str:
    if column_name not in existing:
        return column_name

    index = 2
    while f"{column_name}_{index}" in existing:
        index += 1
    return f"{column_name}_{index}"


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _to_text_series(series: pd.Series) -> pd.Series:
    return series.where(series.notna(), "").astype(str)


def _with_normalized_merge_columns(
    frame: pd.DataFrame, key_columns: list[str], prefix: str
) -> tuple[pd.DataFrame, list[str]]:
    normalized = frame.copy()
    normalized_columns: list[str] = []
    for index, key_column in enumerate(key_columns):
        normalized_column = f"__merge_key_{prefix}_{index}"
        normalized[normalized_column] = normalized[key_column].astype("string")
        normalized_columns.append(normalized_column)
    return normalized, normalized_columns


def _is_excel_vlookup(operation: VLookupOperationConfig) -> bool:
    return all(
        [
            operation.lookup_value_column,
            operation.table_array_sheet,
            operation.table_array_lookup_column,
            operation.col_index_num is not None,
        ]
    )


def _is_legacy_vlookup(operation: VLookupOperationConfig) -> bool:
    return bool(
        operation.base_key_columns
        or operation.lookup_key_columns
        or operation.return_columns
        or operation.lookup_sheet
        or operation.lookup_mode
    )


def _resolve_vlookup_sheet_name(
    all_sheets: dict[str, pd.DataFrame], requested_sheet: str
) -> str:
    if requested_sheet in all_sheets:
        return requested_sheet

    if "__transformed" in requested_sheet:
        source_name = requested_sheet.split("__transformed")[0]
        canonical_transformed_name = f"{source_name}__transformed"
        if canonical_transformed_name in all_sheets:
            return canonical_transformed_name

    return requested_sheet


def _resolve_excel_return_column(
    lookup_frame: pd.DataFrame,
    table_array_lookup_column: str,
    col_index_num: int,
    operation_index: int,
) -> str:
    if table_array_lookup_column not in lookup_frame.columns:
        raise ValueError(
            f"vlookup operation {operation_index + 1} lookup column '{table_array_lookup_column}' was not found"
        )

    if isinstance(col_index_num, bool) or not isinstance(col_index_num, int):
        raise ValueError(
            f"vlookup operation {operation_index + 1} col_index_num must be an integer"
        )

    if col_index_num < 1:
        raise ValueError(
            f"vlookup operation {operation_index + 1} col_index_num must be >= 1"
        )

    all_columns = list(lookup_frame.columns)
    lookup_start = all_columns.index(table_array_lookup_column)
    table_array_columns = all_columns[lookup_start:]

    if col_index_num > len(table_array_columns):
        raise ValueError(
            f"vlookup operation {operation_index + 1} col_index_num={col_index_num} is out of bounds for table_array width {len(table_array_columns)}"
        )

    return table_array_columns[col_index_num - 1]


def _apply_excel_vlookup(
    base_frame: pd.DataFrame,
    operation: VLookupOperationConfig,
    operation_index: int,
    lookup_frame: pd.DataFrame,
) -> pd.DataFrame:
    lookup_value_column = operation.lookup_value_column or ""
    table_lookup_column = operation.table_array_lookup_column or ""
    col_index_num = operation.col_index_num or 0

    _require_columns(
        base_frame,
        [lookup_value_column],
        f"vlookup operation {operation_index + 1} lookup_value column",
    )
    _require_columns(
        lookup_frame,
        [table_lookup_column],
        f"vlookup operation {operation_index + 1} table_array lookup column",
    )

    return_column = _resolve_excel_return_column(
        lookup_frame,
        table_lookup_column,
        col_index_num,
        operation_index,
    )
    output_column = _unique_column_name(
        operation.output_column or return_column, list(base_frame.columns)
    )

    exact_match = operation.range_lookup is False
    if exact_match:
        lookup_series = (
            lookup_frame[[table_lookup_column, return_column]]
            .assign(__excel_lookup_key_norm=lookup_frame[table_lookup_column].astype("string"))
            .drop_duplicates(subset=["__excel_lookup_key_norm"], keep="first")
            .set_index("__excel_lookup_key_norm")[return_column]
        )
        base_lookup_key = base_frame[lookup_value_column].astype("string")
        result = base_frame.copy()
        result[output_column] = base_lookup_key.map(lookup_series).fillna("#N/A")
        return result

    # Excel approximate mode: largest key <= lookup_value, with an ordered lookup column.
    lookup_numeric = pd.to_numeric(lookup_frame[table_lookup_column], errors="coerce")
    if lookup_numeric.isna().any():
        raise ValueError(
            f"vlookup operation {operation_index + 1} approximate mode requires numeric lookup column values without blanks"
        )
    if not lookup_numeric.is_monotonic_increasing:
        raise ValueError(
            f"vlookup operation {operation_index + 1} approximate mode requires lookup column sorted ascending"
        )

    base_numeric = pd.to_numeric(base_frame[lookup_value_column], errors="coerce")
    lookup_data = lookup_frame[[table_lookup_column, return_column]].copy()
    lookup_data["__lookup_numeric"] = lookup_numeric
    lookup_data = lookup_data.drop_duplicates(subset=[table_lookup_column], keep="first")
    lookup_data = lookup_data.sort_values("__lookup_numeric", kind="mergesort")

    sorted_keys = lookup_data["__lookup_numeric"].to_numpy()
    sorted_values = lookup_data[return_column].to_numpy()

    output_values: list[object] = []
    for value in base_numeric:
        if pd.isna(value):
            output_values.append("#N/A")
            continue
        index = sorted_keys.searchsorted(value, side="right") - 1
        if index < 0:
            output_values.append("#N/A")
            continue
        matched_value = sorted_values[index]
        output_values.append("" if pd.isna(matched_value) else matched_value)

    result = base_frame.copy()
    result[output_column] = output_values
    return result


def _build_concat_part_series(
    base_frame: pd.DataFrame,
    base_sheet: str,
    all_sheets: dict[str, pd.DataFrame],
    part: ConcatPartConfig,
    operation_index: int,
) -> pd.Series:
    source_frame = _require_sheet(all_sheets, part.sheet)
    _require_columns(source_frame, [part.column], f"concat operation {operation_index + 1}")

    if part.sheet == base_sheet:
        _require_columns(
            base_frame, [part.column], f"concat operation {operation_index + 1} base sheet"
        )
        return base_frame[part.column]

    if not part.join_keys:
        raise ValueError(
            f"concat operation {operation_index + 1} part '{part.column}' requires join_keys for cross-sheet references"
        )

    base_keys = [mapping.base_column for mapping in part.join_keys]
    source_keys = [mapping.source_column for mapping in part.join_keys]

    _require_columns(
        base_frame,
        base_keys,
        f"concat operation {operation_index + 1} base join keys",
    )
    _require_columns(
        source_frame,
        source_keys,
        f"concat operation {operation_index + 1} source join keys",
    )

    lookup_subset = source_frame[source_keys + [part.column]].copy()
    renamed_lookup = {
        source_key: base_key
        for base_key, source_key in zip(base_keys, source_keys, strict=True)
    }
    lookup_subset = lookup_subset.rename(columns=renamed_lookup)
    lookup_subset = lookup_subset.drop_duplicates(subset=base_keys, keep="first")

    lookup_column_name = f"__concat_part_{operation_index}_{part.column}"
    lookup_subset = lookup_subset.rename(columns={part.column: lookup_column_name})
    base_keys_frame = base_frame[base_keys].copy()
    left_with_keys, merge_columns = _with_normalized_merge_columns(
        base_keys_frame, base_keys, "concat"
    )
    right_with_keys, _ = _with_normalized_merge_columns(
        lookup_subset, base_keys, "concat"
    )
    merged = left_with_keys.merge(
        right_with_keys[merge_columns + [lookup_column_name]],
        on=merge_columns,
        how="left",
    )
    return merged[lookup_column_name]


def apply_concat_operations(
    base_frame: pd.DataFrame,
    base_sheet: str,
    all_sheets: dict[str, pd.DataFrame],
    operations: list[ConcatOperationConfig],
) -> pd.DataFrame:
    transformed = base_frame.copy()

    for operation_index, operation in enumerate(operations):
        if len(operation.parts) < 2:
            raise ValueError(
                f"concat operation {operation_index + 1} must include at least two parts"
            )

        part_series = [
            _to_text_series(
                _build_concat_part_series(
                    transformed,
                    base_sheet,
                    all_sheets,
                    part,
                    operation_index,
                )
            )
            for part in operation.parts
        ]

        output_series = part_series[0]
        for series in part_series[1:]:
            output_series = output_series + operation.delimiter + series

        output_name = _unique_column_name(operation.output_column, list(transformed.columns))
        transformed[output_name] = output_series

    return transformed


def _apply_exact_vlookup(
    base_frame: pd.DataFrame,
    operation: VLookupOperationConfig,
    operation_index: int,
    lookup_frame: pd.DataFrame,
) -> pd.DataFrame:
    if len(operation.base_key_columns) != len(operation.lookup_key_columns):
        raise ValueError(
            f"vlookup operation {operation_index + 1} requires the same number of base and lookup key columns"
        )

    _require_columns(
        base_frame,
        operation.base_key_columns,
        f"vlookup operation {operation_index + 1} base keys",
    )
    _require_columns(
        lookup_frame,
        operation.lookup_key_columns,
        f"vlookup operation {operation_index + 1} lookup keys",
    )
    requested_return_columns = _unique_preserve_order(operation.return_columns)
    _require_columns(
        lookup_frame,
        requested_return_columns,
        f"vlookup operation {operation_index + 1} return columns",
    )

    key_mapping = {
        lookup_key: base_key
        for base_key, lookup_key in zip(
            operation.base_key_columns, operation.lookup_key_columns, strict=True
        )
    }
    non_key_return_columns = [
        column
        for column in requested_return_columns
        if column not in operation.lookup_key_columns
    ]

    lookup_subset_columns = _unique_preserve_order(
        operation.lookup_key_columns + non_key_return_columns
    )
    lookup_subset = lookup_frame[lookup_subset_columns].copy()
    lookup_subset = lookup_subset.rename(
        columns={lookup_key: base_key for lookup_key, base_key in key_mapping.items()}
    )

    renamed_return_columns = {
        return_column: f"__vlookup_{operation_index}_{return_column}"
        for return_column in non_key_return_columns
    }
    lookup_subset = lookup_subset.rename(columns=renamed_return_columns)
    lookup_subset = lookup_subset.drop_duplicates(
        subset=operation.base_key_columns, keep="first"
    )
    left_with_keys, merge_columns = _with_normalized_merge_columns(
        base_frame, operation.base_key_columns, "legacy"
    )
    right_with_keys, _ = _with_normalized_merge_columns(
        lookup_subset, operation.base_key_columns, "legacy"
    )
    merged = left_with_keys.merge(
        right_with_keys[merge_columns + list(renamed_return_columns.values())],
        on=merge_columns,
        how="left",
    )

    for return_column in requested_return_columns:
        target_name = _unique_column_name(
            f"{operation.output_prefix}{return_column}", list(merged.columns)
        )
        if return_column in key_mapping:
            merged[target_name] = merged[key_mapping[return_column]]
        else:
            merged[target_name] = merged[renamed_return_columns[return_column]]

    temp_columns = list(renamed_return_columns.values()) + merge_columns
    return merged.drop(columns=temp_columns)


def _apply_nearest_vlookup(
    base_frame: pd.DataFrame,
    operation: VLookupOperationConfig,
    operation_index: int,
    lookup_frame: pd.DataFrame,
) -> pd.DataFrame:
    if len(operation.base_key_columns) != 1 or len(operation.lookup_key_columns) != 1:
        raise ValueError(
            f"vlookup operation {operation_index + 1} nearest mode requires exactly one base key and one lookup key"
        )

    base_key = operation.base_key_columns[0]
    lookup_key = operation.lookup_key_columns[0]

    _require_columns(base_frame, [base_key], f"vlookup operation {operation_index + 1} base key")
    _require_columns(
        lookup_frame,
        [lookup_key] + operation.return_columns,
        f"vlookup operation {operation_index + 1} lookup data",
    )

    lookup_numeric = pd.to_numeric(lookup_frame[lookup_key], errors="coerce")
    base_numeric = pd.to_numeric(base_frame[base_key], errors="coerce")

    if lookup_numeric.notna().sum() == 0:
        raise ValueError(
            f"vlookup operation {operation_index + 1} nearest lookup requires numeric lookup key values"
        )

    result_frame = base_frame.copy()

    for return_column in operation.return_columns:
        output_name = _unique_column_name(
            f"{operation.output_prefix}{return_column}", list(result_frame.columns)
        )
        output_values: list[object] = []

        for value in base_numeric:
            if pd.isna(value):
                output_values.append("")
                continue

            distances = (lookup_numeric - value).abs()
            if distances.notna().sum() == 0:
                output_values.append("")
                continue

            nearest_index = distances.idxmin(skipna=True)
            matched_value = lookup_frame.loc[nearest_index, return_column]
            output_values.append("" if pd.isna(matched_value) else matched_value)

        result_frame[output_name] = output_values

    return result_frame


def apply_vlookup_operations(
    base_frame: pd.DataFrame,
    all_sheets: dict[str, pd.DataFrame],
    operations: list[VLookupOperationConfig],
) -> pd.DataFrame:
    transformed = base_frame.copy()

    for operation_index, operation in enumerate(operations):
        if _is_excel_vlookup(operation):
            requested_sheet = operation.table_array_sheet or ""
            resolved_sheet = _resolve_vlookup_sheet_name(all_sheets, requested_sheet)
            lookup_frame = _require_sheet(all_sheets, resolved_sheet)
            transformed = _apply_excel_vlookup(
                transformed,
                operation,
                operation_index,
                lookup_frame,
            )
            continue

        if _is_legacy_vlookup(operation):
            if not operation.lookup_sheet:
                raise ValueError(
                    f"vlookup operation {operation_index + 1} lookup_sheet is required for legacy mode"
                )
            if not operation.return_columns:
                raise ValueError(
                    f"vlookup operation {operation_index + 1} requires at least one return column"
                )
            if not operation.base_key_columns or not operation.lookup_key_columns:
                raise ValueError(
                    f"vlookup operation {operation_index + 1} requires base_key_columns and lookup_key_columns for legacy mode"
                )

            resolved_sheet = _resolve_vlookup_sheet_name(all_sheets, operation.lookup_sheet)
            lookup_frame = _require_sheet(all_sheets, resolved_sheet)
            lookup_mode = operation.lookup_mode or "exact"

            if lookup_mode == "exact":
                transformed = _apply_exact_vlookup(
                    transformed,
                    operation,
                    operation_index,
                    lookup_frame,
                )
            else:
                if not operation.advanced_multi_key:
                    raise ValueError(
                        f"vlookup operation {operation_index + 1} nearest mode is available only when advanced_multi_key is enabled"
                    )
                transformed = _apply_nearest_vlookup(
                    transformed,
                    operation,
                    operation_index,
                    lookup_frame,
                )
            continue

        raise ValueError(
            f"vlookup operation {operation_index + 1} is missing required fields. Provide Excel-style fields or legacy fields."
        )

    return transformed


def _generate_result_sheet_name(base_sheet: str, sheet_names: list[str]) -> str:
    candidate = f"{base_sheet}__transformed"
    if candidate not in sheet_names:
        return candidate

    index = 2
    while f"{candidate}_{index}" in sheet_names:
        index += 1
    return f"{candidate}_{index}"


def apply_transform_pipeline(
    all_sheets: dict[str, pd.DataFrame], config: TransformConfig
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    _require_sheet(all_sheets, config.base_sheet)

    transformed_frame = all_sheets[config.base_sheet].copy()

    transformed_frame = apply_concat_operations(
        transformed_frame,
        config.base_sheet,
        all_sheets,
        config.concat_operations,
    )
    # Make the concat output addressable as `<base_sheet>__transformed` during this run.
    runtime_sheets = dict(all_sheets)
    runtime_sheets[f"{config.base_sheet}__transformed"] = transformed_frame
    transformed_frame = apply_vlookup_operations(
        transformed_frame,
        runtime_sheets,
        config.vlookup_operations,
    )

    result_name = _generate_result_sheet_name(config.base_sheet, list(all_sheets.keys()))
    output_sheets = dict(all_sheets)
    output_sheets[result_name] = transformed_frame

    return output_sheets, [result_name]


def run_default_automation(csv_text: str) -> pd.DataFrame:
    frame = pd.read_csv(StringIO(csv_text))
    return apply_default_automation(frame)
