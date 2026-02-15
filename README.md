# gsheets-automations

Simple starter project for **Python + React** spreadsheet workflows focused on gussets / Excel / CSV automations.

## What is included

- **Backend**: FastAPI service that accepts CSV text, normalizes headers, and runs starter automation rules.
- **Frontend**: React app where you can paste CSV data and preview automated output.

## Backend (Python)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API endpoints:

- `GET /api/health`
- `POST /api/automate`

## Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Starter automation behavior

When posting CSV to `/api/automate`:

1. Column names are normalized to `snake_case` lowercase.
2. If `quantity` and `unit_price` exist, a `line_total` column is added.
3. If `product` exists, an `is_gusset` boolean column is added (simple text match).

This gives you a clean base for additional Excel/CSV/Google Sheets automation logic.
