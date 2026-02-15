import { useMemo, useState } from 'react'

const sampleCsv = `product,quantity,unit price
Gusset Bag Small,4,3.75
Tape Roll,2,1.10
Gusset Bag Large,1,5.20`

export function App() {
  const [inputTab, setInputTab] = useState('upload')
  const [csvText, setCsvText] = useState(sampleCsv)
  const [rows, setRows] = useState([])
  const [columns, setColumns] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploadLoading, setUploadLoading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [sheetResults, setSheetResults] = useState({})
  const [activeSheet, setActiveSheet] = useState('')

  const hasResults = useMemo(() => rows.length > 0 && columns.length > 0, [rows, columns])
  const sheetNames = useMemo(() => Object.keys(sheetResults), [sheetResults])
  const hasUploadResults = useMemo(() => sheetNames.length > 0, [sheetNames])
  const activeSheetResult = activeSheet ? sheetResults[activeSheet] : undefined

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

  const runUploadAutomation = async () => {
    if (!selectedFile) {
      setUploadError('Please select a file before running upload automation')
      return
    }

    setUploadLoading(true)
    setUploadError('')

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const response = await fetch('http://localhost:8000/api/automate/upload', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const payload = await response.json()
        throw new Error(payload.detail ?? 'Upload automation failed')
      }

      const payload = await response.json()
      const sheets = payload.sheets ?? {}
      const names = Object.keys(sheets)
      setSheetResults(sheets)
      setActiveSheet(names[0] ?? '')
    } catch (err) {
      setUploadError(err.message)
      setSheetResults({})
      setActiveSheet('')
    } finally {
      setUploadLoading(false)
    }
  }

  const renderTable = (tableColumns, tableRows) => (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            {tableColumns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tableRows.map((row, rowIndex) => (
            <tr key={`row-${rowIndex}`}>
              {tableColumns.map((column) => (
                <td key={`${rowIndex}-${column}`}>{String(row[column] ?? '')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  return (
    <main className="page">
      <h1>Python + React Spreadsheet Automations</h1>
      <p>
        Starter workflow for Google Sheets exports / Excel / CSV automations. Use CSV text input
        or upload exported CSV/XLS/XLSX files (10 MB max) and inspect normalized output.
      </p>

      <div className="input-tabs">
        <button
          type="button"
          className={`input-tab ${inputTab === 'upload' ? 'active' : ''}`}
          onClick={() => setInputTab('upload')}
        >
          Spreadsheet Upload
        </button>
        <button
          type="button"
          className={`input-tab ${inputTab === 'csv' ? 'active' : ''}`}
          onClick={() => setInputTab('csv')}
        >
          CSV Paste
        </button>
      </div>

      {inputTab === 'upload' ? (
        <section className="panel">
          <h2>Upload Spreadsheet</h2>
          <label htmlFor="file-input">File Upload (.csv, .xlsx, .xls)</label>
          <input
            id="file-input"
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
          />
          {selectedFile ? <p className="file-meta">Selected: {selectedFile.name}</p> : null}

          <button onClick={runUploadAutomation} disabled={uploadLoading}>
            {uploadLoading ? 'Running Upload…' : 'Run Upload'}
          </button>

          {uploadError ? <p className="error">{uploadError}</p> : null}

          {hasUploadResults ? (
            <section>
              <h3>Upload Output Preview</h3>
              <div className="sheet-tabs">
                {sheetNames.map((sheetName) => (
                  <button
                    key={sheetName}
                    className={`sheet-tab ${sheetName === activeSheet ? 'active' : ''}`}
                    onClick={() => setActiveSheet(sheetName)}
                    type="button"
                  >
                    {sheetName}
                  </button>
                ))}
              </div>
              {activeSheetResult ? (
                renderTable(activeSheetResult.columns ?? [], activeSheetResult.rows ?? [])
              ) : (
                <p>No sheet preview available.</p>
              )}
            </section>
          ) : null}
        </section>
      ) : (
        <section className="panel">
          <h2>Paste CSV</h2>
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
              <h3>CSV Output Preview</h3>
              {renderTable(columns, rows)}
            </section>
          ) : null}
        </section>
      )}
    </main>
  )
}
