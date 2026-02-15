# gsheets-automations

Simple starter project for **Python + React** spreadsheet workflows focused on gheets / Excel / CSV automations.

## What is included

- **Backend**: FastAPI service that accepts CSV text, normalizes headers, and runs starter automation rules.
- **Frontend**: React app where you can paste CSV text or upload CSV/Excel files and preview automated output.

## Backend (Python)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API endpoints:

- `GET /api/health`
- `POST /api/automate`
- `POST /api/automate/upload`

## Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Upload formats

Supported upload formats:

- `.csv`
- `.xlsx`
- `.xls`

Google Sheets support is handled via **exported files**. From Google Sheets, use:

- File -> Download -> Comma Separated Values (`.csv`) or
- File -> Download -> Microsoft Excel (`.xlsx`)

Then upload the downloaded file in the frontend.

Upload limit: **10 MB** per file.

## Starter automation behavior

When posting CSV text to `/api/automate` or files to `/api/automate/upload`:

1. Column names are normalized to `snake_case` lowercase.
2. If `quantity` and `unit_price` exist, a `line_total` column is added.
3. If `product` exists, an `is_gusset` boolean column is added (simple text match).

For Excel uploads, all worksheets are processed and returned as per-sheet results.

## API examples

CSV text (existing endpoint):

```bash
curl -X POST http://localhost:8000/api/automate \
  -H "Content-Type: application/json" \
  -d '{"csv_text":"product,quantity,unit price\nGusset Bag Small,4,3.75"}'
```

CSV/XLS/XLSX upload:

```bash
curl -X POST http://localhost:8000/api/automate/upload \
  -F "file=@/absolute/path/to/spreadsheet.xlsx"
```

Upload response shape:

```json
{
  "source_type": "excel",
  "sheets": {
    "Sheet1": {
      "columns": ["product", "quantity", "unit_price", "line_total", "is_gusset"],
      "rows": [{ "product": "Gusset Bag Small", "quantity": 4 }]
    }
  }
}
```

This gives you a clean base for additional Excel/CSV/Google Sheets automation logic.
