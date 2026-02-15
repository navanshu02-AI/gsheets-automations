import { useMemo, useState } from 'react'

const sampleCsv = `product,quantity,unit price
Gusset Bag Small,4,3.75
Tape Roll,2,1.10
Gusset Bag Large,1,5.20`

export function App() {
  const [csvText, setCsvText] = useState(sampleCsv)
  const [rows, setRows] = useState([])
  const [columns, setColumns] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const hasResults = useMemo(() => rows.length > 0 && columns.length > 0, [rows, columns])

  const runAutomation = async () => {
    setLoading(true)
    setError('')

    try {
      const response = await fetch('http://localhost:8000/api/automate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv_text: csvText }),
      })

      if (!response.ok) {
        const payload = await response.json()
        throw new Error(payload.detail ?? 'Automation failed')
      }

      const payload = await response.json()
      setColumns(payload.columns)
      setRows(payload.rows)
    } catch (err) {
      setError(err.message)
      setColumns([])
      setRows([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page">
      <h1>Python + React Spreadsheet Automations</h1>
      <p>
        Starter workflow for gussets / Excel / CSV automations. Paste CSV data, run automation,
        and inspect normalized output.
      </p>

      <label htmlFor="csv-input">CSV Input</label>
      <textarea
        id="csv-input"
        value={csvText}
        onChange={(event) => setCsvText(event.target.value)}
        rows={10}
      />

      <button onClick={runAutomation} disabled={loading}>
        {loading ? 'Running…' : 'Run Automation'}
      </button>

      {error ? <p className="error">{error}</p> : null}

      {hasResults ? (
        <section>
          <h2>Output Preview</h2>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rowIndex) => (
                  <tr key={`row-${rowIndex}`}>
                    {columns.map((column) => (
                      <td key={`${rowIndex}-${column}`}>{String(row[column] ?? '')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </main>
  )
}
