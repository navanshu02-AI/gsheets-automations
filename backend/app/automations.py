from __future__ import annotations

from io import BytesIO, StringIO
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
    lookup_mode: Literal["exact", "nearest"]
    base_key_columns: list[str]
    lookup_sheet: str
    lookup_key_columns: list[str]
    return_columns: list[str]
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
    sheets = pd.read_excel(BytesIO(file_bytes), sheet_name=None)
    return {str(sheet_name): frame for sheet_name, frame in sheets.items()}


def run_automation_on_sheets(sheets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {
        sheet_name: apply_default_automation(frame)
        for sheet_name, frame in sheets.items()
    }


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


def _to_text_series(series: pd.Series) -> pd.Series:
    return series.where(series.notna(), "").astype(str)


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

    merged = base_frame[base_keys].merge(lookup_subset, on=base_keys, how="left")
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
    _require_columns(
        lookup_frame,
        operation.return_columns,
        f"vlookup operation {operation_index + 1} return columns",
    )

    lookup_subset = lookup_frame[operation.lookup_key_columns + operation.return_columns].copy()
    lookup_subset = lookup_subset.rename(
        columns={
            lookup_key: base_key
            for base_key, lookup_key in zip(
                operation.base_key_columns, operation.lookup_key_columns, strict=True
            )
        }
    )

    renamed_return_columns = {
        return_column: f"__vlookup_{operation_index}_{return_column}"
        for return_column in operation.return_columns
    }
    lookup_subset = lookup_subset.rename(columns=renamed_return_columns)
    lookup_subset = lookup_subset.drop_duplicates(
        subset=operation.base_key_columns, keep="first"
    )

    merged = base_frame.merge(lookup_subset, on=operation.base_key_columns, how="left")

    for return_column in operation.return_columns:
        target_name = _unique_column_name(
            f"{operation.output_prefix}{return_column}", list(merged.columns)
        )
        merged[target_name] = merged[renamed_return_columns[return_column]]

    temp_columns = list(renamed_return_columns.values())
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
        if not operation.return_columns:
            raise ValueError(
                f"vlookup operation {operation_index + 1} requires at least one return column"
            )

        lookup_frame = _require_sheet(all_sheets, operation.lookup_sheet)

        if operation.lookup_mode == "exact":
            transformed = _apply_exact_vlookup(
                transformed,
                operation,
                operation_index,
                lookup_frame,
            )
        else:
            transformed = _apply_nearest_vlookup(
                transformed,
                operation,
                operation_index,
                lookup_frame,
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
    transformed_frame = apply_vlookup_operations(
        transformed_frame,
        all_sheets,
        config.vlookup_operations,
    )

    result_name = _generate_result_sheet_name(config.base_sheet, list(all_sheets.keys()))
    output_sheets = dict(all_sheets)
    output_sheets[result_name] = transformed_frame

    return output_sheets, [result_name]


def run_default_automation(csv_text: str) -> pd.DataFrame:
    frame = pd.read_csv(StringIO(csv_text))
    return apply_default_automation(frame)
