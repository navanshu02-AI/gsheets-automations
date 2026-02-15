from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .automations import (
    parse_csv_bytes,
    parse_excel_bytes,
    run_automation_on_sheets,
    run_default_automation,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
CSV_EXTENSIONS = {".csv"}
EXCEL_EXTENSIONS = {".xlsx", ".xls"}
CSV_CONTENT_TYPES = {"text/csv", "application/csv", "application/vnd.ms-excel"}
EXCEL_CONTENT_TYPES = {
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

app = FastAPI(title="Spreadsheet Automations API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AutomationRequest(BaseModel):
    csv_text: str


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/automate")
def automate(payload: AutomationRequest) -> dict[str, object]:
    if not payload.csv_text.strip():
        raise HTTPException(status_code=400, detail="csv_text cannot be empty")

    try:
        automated_frame = run_default_automation(payload.csv_text)
    except Exception as exc:  # pragma: no cover - lightweight starter app
        raise HTTPException(status_code=400, detail=f"Unable to process CSV: {exc}") from exc

    return {
        "columns": list(automated_frame.columns),
        "rows": automated_frame.fillna("").to_dict(orient="records"),
    }


def _serialize_sheet_results(sheets: dict[str, object]) -> dict[str, object]:
    return {
        sheet_name: {
            "columns": list(frame.columns),
            "rows": frame.fillna("").to_dict(orient="records"),
        }
        for sheet_name, frame in sheets.items()
    }


@app.post("/api/automate/upload")
async def automate_upload(file: UploadFile = File(...)) -> dict[str, object]:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    content_type = (file.content_type or "").lower()

    if extension == ".gsheet":
        raise HTTPException(
            status_code=400,
            detail="Google Sheets shortcut files are not supported. Upload exported CSV/XLSX from Google Sheets.",
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded file exceeds 10 MB limit",
        )

    is_csv = extension in CSV_EXTENSIONS or (
        not extension and content_type in CSV_CONTENT_TYPES
    )
    is_excel = extension in EXCEL_EXTENSIONS or (
        not extension and content_type in EXCEL_CONTENT_TYPES
    )

    try:
        if is_csv:
            automated_sheets = run_automation_on_sheets(
                {"data": parse_csv_bytes(file_bytes)}
            )
            return {
                "source_type": "csv",
                "sheets": _serialize_sheet_results(automated_sheets),
            }

        if is_excel:
            parsed_sheets = parse_excel_bytes(file_bytes)
            automated_sheets = run_automation_on_sheets(parsed_sheets)
            return {
                "source_type": "excel",
                "sheets": _serialize_sheet_results(automated_sheets),
            }
    except Exception as exc:  # pragma: no cover - lightweight starter app
        raise HTTPException(
            status_code=400, detail=f"Unable to process uploaded file: {exc}"
        ) from exc

    raise HTTPException(
        status_code=400,
        detail="Unsupported file format. Upload CSV, XLSX, or XLS exported from Google Sheets.",
    )
