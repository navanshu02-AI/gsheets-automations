# gsheets-automations

Simple starter project for **Python + React** spreadsheet workflows focused on gheets / Excel / CSV automations.

## What is included

- **Backend**: FastAPI service that accepts CSV text, normalizes headers, and runs starter automation rules.
- **Frontend**: React app where you can upload CSV/Excel files and preview automated output.

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
  },
  "transforms_applied": false,
  "result_sheets": []
}
```

## Advanced upload transforms

`POST /api/automate/upload` accepts an optional multipart `config` field (JSON string).
If provided, the backend runs:

1. All `concat_operations` in order
2. All `vlookup_operations` in order

Transformed data is returned as a new sheet (`<base_sheet>__transformed`, collision-safe suffixes),
while original sheets remain unchanged.

Example `config`:

```json
{
  "base_sheet": "orders",
  "concat_operations": [
    {
      "output_column": "full_name",
      "delimiter": " ",
      "parts": [
        { "sheet": "orders", "column": "first_name", "join_keys": [] },
        {
          "sheet": "customers",
          "column": "last_name",
          "join_keys": [{ "base_column": "customer_id", "source_column": "customer_id" }]
        }
      ]
    }
  ],
  "vlookup_operations": [
    {
      "lookup_value_column": "sku",
      "table_array_sheet": "catalog",
      "table_array_lookup_column": "sku",
      "col_index_num": 2,
      "range_lookup": false,
      "output_column": "catalog_category"
    }
  ]
}
```

Excel mapping for selectable VLOOKUP UI:

`VLOOKUP(lookup_value, table_array, col_index_num, [range_lookup])`

- `lookup_value` -> selected base-sheet lookup value column (per row)
- `table_array` -> selected lookup sheet, starting from selected lookup column
- `col_index_num` -> auto-computed from selected return column position (1-based)
- `range_lookup` -> `FALSE` exact match, `TRUE` approximate match

`range_lookup=TRUE` behavior:

- Uses the largest lookup key less than or equal to `lookup_value`
- Lookup column must be numeric and sorted ascending

Legacy advanced mode:

- Optional and backward compatible
- Uses legacy fields (`lookup_mode`, `base_key_columns`, `lookup_key_columns`, `return_columns`)
- `lookup_mode=nearest` is allowed only with `advanced_multi_key=true`

Multipart upload with config:

```bash
curl -X POST http://localhost:8000/api/automate/upload \
  -F "file=@/absolute/path/to/spreadsheet.xlsx" \
  -F 'config={"base_sheet":"orders","concat_operations":[],"vlookup_operations":[{"lookup_value_column":"sku","table_array_sheet":"catalog","table_array_lookup_column":"sku","col_index_num":2,"range_lookup":false,"output_column":"catalog_category"}]}'
```

This gives you a clean base for additional Excel/CSV/Google Sheets automation logic.
