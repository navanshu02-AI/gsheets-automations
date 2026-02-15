from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .automations import run_default_automation

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
