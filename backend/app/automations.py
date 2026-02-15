from __future__ import annotations

from io import BytesIO, StringIO

import pandas as pd


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


def run_default_automation(csv_text: str) -> pd.DataFrame:
    frame = pd.read_csv(StringIO(csv_text))
    return apply_default_automation(frame)
