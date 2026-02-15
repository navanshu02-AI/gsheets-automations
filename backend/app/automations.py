from __future__ import annotations

from io import StringIO

import pandas as pd


def run_default_automation(csv_text: str) -> pd.DataFrame:
    """Apply a simple starter automation for spreadsheet workflows."""
    frame = pd.read_csv(StringIO(csv_text))

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
