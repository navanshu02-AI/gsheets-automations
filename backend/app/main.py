from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from .automations import (
    TransformConfig,
    apply_transform_pipeline,
    parse_csv_bytes,
    parse_excel_bytes,
    run_automation_on_sheets,
    run_default_automation,
)
from .labels import (
    extract_classic_sticker_rows,
    extract_label_rows,
    generate_classic_stickers_pdf,
    generate_labels_pdf,
    parse_classic_sticker_config,
    suggest_classic_sticker_filename,
    suggest_download_filename,
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

default_cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", ",".join(default_cors_origins)).split(",")
    if origin.strip()
]
cors_origin_regex = os.getenv("CORS_ORIGIN_REGEX")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
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


def _parse_transform_config(config: str | None) -> TransformConfig | None:
    if config is None:
        return None

    if not config.strip():
        return None

    try:
        payload = json.loads(config)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid config JSON: {exc.msg}") from exc

    try:
        return TransformConfig.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid transform config: {exc}") from exc


def _build_classic_sticker_response(
    automated_sheets: dict[str, object],
    classic_config: dict[str, object],
    filename_hint: str,
) -> Response:
    sheet_name = str(classic_config["sheet_name"]).strip()
    label_size = str(classic_config["label_size"]).strip().lower()
    padding_in = float(classic_config["padding_in"])
    fields = list(classic_config["fields"])

    if sheet_name not in automated_sheets:
        raise ValueError(
            f"Sheet '{sheet_name}' was not found in the uploaded file. Choose an existing sheet and try again."
        )

    sticker_rows = extract_classic_sticker_rows(automated_sheets[sheet_name], fields)
    if not sticker_rows:
        raise ValueError(
            "No printable rows were found for classic stickers. Check the selected fields and make sure the chosen sheet has values."
        )

    pdf_bytes = generate_classic_stickers_pdf(
        sticker_rows,
        label_size=label_size,
        padding_in=padding_in,
    )
    filename = suggest_classic_sticker_filename(filename_hint, label_size)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/automate/upload", response_model=None)
async def automate_upload(
    file: UploadFile = File(...),
    config: str | None = Form(default=None),
    mode: str | None = Form(default=None),
    portrait: bool = Form(default=False),
    padding_in: float = Form(default=0.25),
    classic_sticker_config: str | None = Form(default=None),
    manual_invoice_number: str | None = Form(default=None),
    manual_po_number: str | None = Form(default=None),
    delivery_sheet: str | None = Form(default=None),
) -> object:
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

    requested_mode = (mode or "").strip().lower()
    parsed_config = (
        None if requested_mode == "classic_stickers_pdf" else _parse_transform_config(config)
    )
    classic_config = (
        parse_classic_sticker_config(classic_sticker_config)
        if requested_mode == "classic_stickers_pdf"
        else None
    )

    try:
        if is_csv:
            parsed_sheets = {"data": parse_csv_bytes(file_bytes)}
            automated_sheets = run_automation_on_sheets(parsed_sheets)

            if requested_mode == "labels_pdf":
                label_rows = extract_label_rows(
                    automated_sheets,
                    filename_hint=filename,
                    invoice_override=manual_invoice_number or "",
                    po_override=manual_po_number or "",
                    preferred_sheet=delivery_sheet or "",
                )
                pdf_bytes = generate_labels_pdf(
                    label_rows, portrait=portrait, padding_in=padding_in
                )
                filename = suggest_download_filename(label_rows)
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )

            if requested_mode == "classic_stickers_pdf":
                return _build_classic_sticker_response(
                    automated_sheets,
                    classic_config or {},
                    filename_hint=filename,
                )

            result_sheets: list[str] = []
            output_sheets = automated_sheets

            if parsed_config is not None:
                output_sheets, result_sheets = apply_transform_pipeline(
                    automated_sheets, parsed_config
                )

            return {
                "source_type": "csv",
                "sheets": _serialize_sheet_results(output_sheets),
                "transforms_applied": bool(result_sheets),
                "result_sheets": result_sheets,
            }

        if is_excel:
            parsed_sheets = parse_excel_bytes(file_bytes)
            automated_sheets = run_automation_on_sheets(parsed_sheets)

            if requested_mode == "labels_pdf":
                label_rows = extract_label_rows(
                    automated_sheets,
                    filename_hint=filename,
                    invoice_override=manual_invoice_number or "",
                    po_override=manual_po_number or "",
                    preferred_sheet=delivery_sheet or "",
                )
                pdf_bytes = generate_labels_pdf(
                    label_rows, portrait=portrait, padding_in=padding_in
                )
                filename = suggest_download_filename(label_rows)
                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )

            if requested_mode == "classic_stickers_pdf":
                return _build_classic_sticker_response(
                    automated_sheets,
                    classic_config or {},
                    filename_hint=filename,
                )

            result_sheets = []
            output_sheets = automated_sheets

            if parsed_config is not None:
                output_sheets, result_sheets = apply_transform_pipeline(
                    automated_sheets, parsed_config
                )

            return {
                "source_type": "excel",
                "sheets": _serialize_sheet_results(output_sheets),
                "transforms_applied": bool(result_sheets),
                "result_sheets": result_sheets,
            }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        message = str(exc).lower()
        if "openpyxl" in message:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Missing dependency 'openpyxl'. Install backend dependencies with: "
                    "pip install -r backend/requirements.txt"
                ),
            ) from exc
        if "reportlab" in message:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Missing dependency 'reportlab'. Install backend dependencies with: "
                    "pip install -r backend/requirements.txt"
                ),
            ) from exc
        raise HTTPException(
            status_code=400, detail=f"Unable to process uploaded file: {exc}"
        ) from exc
    except Exception as exc:  # pragma: no cover - lightweight starter app
        raise HTTPException(
            status_code=400, detail=f"Unable to process uploaded file: {exc}"
        ) from exc

    raise HTTPException(
        status_code=400,
        detail="Unsupported file format. Upload CSV, XLSX, or XLS exported from Google Sheets.",
    )
