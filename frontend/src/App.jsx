import { useMemo, useState } from 'react'

const createJoinKey = () => ({ base_column: '', source_column: '' })
const createConcatPart = () => ({ sheet: '', column: '', join_keys: [] })
const createConcatOperation = () => ({
  output_column: '',
  delimiter: '',
  parts: [createConcatPart(), createConcatPart()],
})
const createVlookupOperation = () => ({
  lookup_mode: 'exact',
  base_key_columns: '',
  lookup_sheet: '',
  lookup_key_columns: '',
  return_columns: '',
  output_prefix: '',
})

const parseCsvList = (value) =>
  value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)

export function App() {
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploadLoading, setUploadLoading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [sheetResults, setSheetResults] = useState({})
  const [activeSheet, setActiveSheet] = useState('')
  const [resultSheets, setResultSheets] = useState([])
  const [transformsApplied, setTransformsApplied] = useState(false)
  const [builderErrors, setBuilderErrors] = useState([])
  const [transformConfig, setTransformConfig] = useState({
    base_sheet: '',
    concat_operations: [],
    vlookup_operations: [],
  })

  const sheetNames = useMemo(() => Object.keys(sheetResults), [sheetResults])
  const hasUploadResults = useMemo(() => sheetNames.length > 0, [sheetNames])
  const activeSheetResult = activeSheet ? sheetResults[activeSheet] : undefined

  const columnsBySheet = useMemo(() => {
    const mapping = {}
    Object.entries(sheetResults).forEach(([sheetName, payload]) => {
      mapping[sheetName] = payload.columns ?? []
    })
    return mapping
  }, [sheetResults])

  const baseSheetColumns = columnsBySheet[transformConfig.base_sheet] ?? []

  const buildTransformConfigPayload = () => {
    const errors = []

    const concatOps = transformConfig.concat_operations.map((operation, operationIndex) => {
      if (!operation.output_column.trim()) {
        errors.push(`Concat operation ${operationIndex + 1}: output column is required`)
      }

      if ((operation.parts ?? []).length < 2) {
        errors.push(`Concat operation ${operationIndex + 1}: at least two parts are required`)
      }

      const parts = (operation.parts ?? []).map((part, partIndex) => {
        if (!part.sheet) {
          errors.push(`Concat operation ${operationIndex + 1}, part ${partIndex + 1}: sheet is required`)
        }
        if (!part.column) {
          errors.push(`Concat operation ${operationIndex + 1}, part ${partIndex + 1}: column is required`)
        }

        const joinKeys = (part.join_keys ?? []).map((mapping, mappingIndex) => {
          if (!mapping.base_column || !mapping.source_column) {
            errors.push(
              `Concat operation ${operationIndex + 1}, part ${partIndex + 1}, join key ${mappingIndex + 1}: both columns are required`
            )
          }
          return {
            base_column: mapping.base_column,
            source_column: mapping.source_column,
          }
        })

        const isCrossSheet = part.sheet && transformConfig.base_sheet && part.sheet !== transformConfig.base_sheet
        if (isCrossSheet && joinKeys.length === 0) {
          errors.push(
            `Concat operation ${operationIndex + 1}, part ${partIndex + 1}: join keys are required for cross-sheet concat`
          )
        }

        return {
          sheet: part.sheet,
          column: part.column,
          join_keys: joinKeys,
        }
      })

      return {
        output_column: operation.output_column,
        delimiter: operation.delimiter,
        parts,
      }
    })

    const vlookupOps = transformConfig.vlookup_operations.map((operation, operationIndex) => {
      const baseKeys = parseCsvList(operation.base_key_columns)
      const lookupKeys = parseCsvList(operation.lookup_key_columns)
      const returnColumns = parseCsvList(operation.return_columns)

      if (!operation.lookup_sheet) {
        errors.push(`VLOOKUP operation ${operationIndex + 1}: lookup sheet is required`)
      }
      if (baseKeys.length === 0) {
        errors.push(`VLOOKUP operation ${operationIndex + 1}: base key columns are required`)
      }
      if (lookupKeys.length === 0) {
        errors.push(`VLOOKUP operation ${operationIndex + 1}: lookup key columns are required`)
      }
      if (returnColumns.length === 0) {
        errors.push(`VLOOKUP operation ${operationIndex + 1}: return columns are required`)
      }

      return {
        lookup_mode: operation.lookup_mode,
        base_key_columns: baseKeys,
        lookup_sheet: operation.lookup_sheet,
        lookup_key_columns: lookupKeys,
        return_columns: returnColumns,
        output_prefix: operation.output_prefix,
      }
    })

    const hasAdvancedOps = concatOps.length > 0 || vlookupOps.length > 0

    if (!hasAdvancedOps) {
      return { payload: null, errors: [] }
    }

    if (!transformConfig.base_sheet) {
      errors.push('Base sheet is required when advanced operations are configured')
    }

    if (errors.length > 0) {
      return { payload: null, errors }
    }

    return {
      payload: {
        base_sheet: transformConfig.base_sheet,
        concat_operations: concatOps,
        vlookup_operations: vlookupOps,
      },
      errors: [],
    }
  }

  const runUploadAutomation = async () => {
    if (!selectedFile) {
      setUploadError('Please select a file before running upload automation')
      return
    }

    const { payload: transformPayload, errors: configErrors } = buildTransformConfigPayload()
    setBuilderErrors(configErrors)
    if (configErrors.length > 0) {
      setUploadError('Please fix transform configuration errors before running upload automation')
      return
    }

    setUploadLoading(true)
    setUploadError('')

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      if (transformPayload) {
        formData.append('config', JSON.stringify(transformPayload))
      }

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
      setResultSheets(payload.result_sheets ?? [])
      setTransformsApplied(Boolean(payload.transforms_applied))
      setActiveSheet(names[0] ?? '')

      if (!transformConfig.base_sheet && names.length > 0) {
        setTransformConfig((current) => ({ ...current, base_sheet: names[0] }))
      }
    } catch (err) {
      setUploadError(err.message)
      setSheetResults({})
      setResultSheets([])
      setTransformsApplied(false)
      setActiveSheet('')
    } finally {
      setUploadLoading(false)
    }
  }

  const setConcatOperation = (operationIndex, updater) => {
    setTransformConfig((current) => {
      const next = [...current.concat_operations]
      next[operationIndex] = updater(next[operationIndex])
      return { ...current, concat_operations: next }
    })
  }

  const setConcatPart = (operationIndex, partIndex, updater) => {
    setConcatOperation(operationIndex, (operation) => {
      const parts = [...operation.parts]
      parts[partIndex] = updater(parts[partIndex])
      return { ...operation, parts }
    })
  }

  const setJoinKey = (operationIndex, partIndex, joinKeyIndex, updater) => {
    setConcatPart(operationIndex, partIndex, (part) => {
      const joinKeys = [...part.join_keys]
      joinKeys[joinKeyIndex] = updater(joinKeys[joinKeyIndex])
      return { ...part, join_keys: joinKeys }
    })
  }

  const setVlookupOperation = (operationIndex, updater) => {
    setTransformConfig((current) => {
      const next = [...current.vlookup_operations]
      next[operationIndex] = updater(next[operationIndex])
      return { ...current, vlookup_operations: next }
    })
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
        Starter workflow for Google Sheets exports / Excel / CSV automations. Upload exported
        CSV/XLS/XLSX files (10 MB max) and inspect normalized output.
      </p>

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

        <section className="builder-section">
          <h3>Advanced Transform Builder</h3>
          <p className="hint">
            Configure concat and VLOOKUP pipeline. If you need sheet/column names, run once first
            to load metadata.
          </p>

            <label htmlFor="base-sheet">Base Sheet</label>
            <select
              id="base-sheet"
              value={transformConfig.base_sheet}
              onChange={(event) =>
                setTransformConfig((current) => ({ ...current, base_sheet: event.target.value }))
              }
            >
              <option value="">Select base sheet</option>
              {sheetNames.map((sheetName) => (
                <option key={sheetName} value={sheetName}>
                  {sheetName}
                </option>
              ))}
            </select>

            <div className="builder-group">
              <div className="builder-header">
                <h4>Concat Operations</h4>
                <button
                  type="button"
                  onClick={() =>
                    setTransformConfig((current) => ({
                      ...current,
                      concat_operations: [...current.concat_operations, createConcatOperation()],
                    }))
                  }
                >
                  Add Concat
                </button>
              </div>

              {transformConfig.concat_operations.map((operation, operationIndex) => (
                <article key={`concat-${operationIndex}`} className="op-card">
                  <div className="op-grid">
                    <label>
                      Output Column
                      <input
                        type="text"
                        value={operation.output_column}
                        onChange={(event) =>
                          setConcatOperation(operationIndex, (current) => ({
                            ...current,
                            output_column: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label>
                      Delimiter
                      <input
                        type="text"
                        value={operation.delimiter}
                        onChange={(event) =>
                          setConcatOperation(operationIndex, (current) => ({
                            ...current,
                            delimiter: event.target.value,
                          }))
                        }
                      />
                    </label>
                  </div>

                  <div className="parts-list">
                    {operation.parts.map((part, partIndex) => {
                      const sourceColumns = columnsBySheet[part.sheet] ?? []
                      const isCrossSheet =
                        part.sheet && transformConfig.base_sheet && part.sheet !== transformConfig.base_sheet

                      return (
                        <div key={`concat-part-${partIndex}`} className="part-card">
                          <div className="op-grid">
                            <label>
                              Source Sheet
                              <select
                                value={part.sheet}
                                onChange={(event) =>
                                  setConcatPart(operationIndex, partIndex, (current) => ({
                                    ...current,
                                    sheet: event.target.value,
                                  }))
                                }
                              >
                                <option value="">Select sheet</option>
                                {sheetNames.map((sheetName) => (
                                  <option key={sheetName} value={sheetName}>
                                    {sheetName}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Source Column
                              <select
                                value={part.column}
                                onChange={(event) =>
                                  setConcatPart(operationIndex, partIndex, (current) => ({
                                    ...current,
                                    column: event.target.value,
                                  }))
                                }
                              >
                                <option value="">Select column</option>
                                {sourceColumns.map((column) => (
                                  <option key={`${part.sheet}-${column}`} value={column}>
                                    {column}
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>

                          {isCrossSheet ? (
                            <div className="join-map">
                              <p>Join Keys</p>
                              {part.join_keys.map((mapping, joinKeyIndex) => (
                                <div key={`join-${joinKeyIndex}`} className="join-row">
                                  <select
                                    value={mapping.base_column}
                                    onChange={(event) =>
                                      setJoinKey(operationIndex, partIndex, joinKeyIndex, (current) => ({
                                        ...current,
                                        base_column: event.target.value,
                                      }))
                                    }
                                  >
                                    <option value="">Base column</option>
                                    {baseSheetColumns.map((column) => (
                                      <option key={`base-${column}`} value={column}>
                                        {column}
                                      </option>
                                    ))}
                                  </select>
                                  <select
                                    value={mapping.source_column}
                                    onChange={(event) =>
                                      setJoinKey(operationIndex, partIndex, joinKeyIndex, (current) => ({
                                        ...current,
                                        source_column: event.target.value,
                                      }))
                                    }
                                  >
                                    <option value="">Source column</option>
                                    {sourceColumns.map((column) => (
                                      <option key={`source-${column}`} value={column}>
                                        {column}
                                      </option>
                                    ))}
                                  </select>
                                  <button
                                    type="button"
                                    className="danger"
                                    onClick={() =>
                                      setConcatPart(operationIndex, partIndex, (current) => ({
                                        ...current,
                                        join_keys: current.join_keys.filter((_, index) => index !== joinKeyIndex),
                                      }))
                                    }
                                  >
                                    Remove Key
                                  </button>
                                </div>
                              ))}
                              <button
                                type="button"
                                onClick={() =>
                                  setConcatPart(operationIndex, partIndex, (current) => ({
                                    ...current,
                                    join_keys: [...current.join_keys, createJoinKey()],
                                  }))
                                }
                              >
                                Add Join Key
                              </button>
                            </div>
                          ) : null}

                          <button
                            type="button"
                            className="danger"
                            onClick={() =>
                              setConcatOperation(operationIndex, (current) => ({
                                ...current,
                                parts: current.parts.filter((_, index) => index !== partIndex),
                              }))
                            }
                          >
                            Remove Part
                          </button>
                        </div>
                      )
                    })}
                  </div>

                  <div className="inline-actions">
                    <button
                      type="button"
                      onClick={() =>
                        setConcatOperation(operationIndex, (current) => ({
                          ...current,
                          parts: [...current.parts, createConcatPart()],
                        }))
                      }
                    >
                      Add Part
                    </button>
                    <button
                      type="button"
                      className="danger"
                      onClick={() =>
                        setTransformConfig((current) => ({
                          ...current,
                          concat_operations: current.concat_operations.filter(
                            (_, index) => index !== operationIndex
                          ),
                        }))
                      }
                    >
                      Remove Concat
                    </button>
                  </div>
                </article>
              ))}
            </div>

            <div className="builder-group">
              <div className="builder-header">
                <h4>VLOOKUP Operations</h4>
                <button
                  type="button"
                  onClick={() =>
                    setTransformConfig((current) => ({
                      ...current,
                      vlookup_operations: [...current.vlookup_operations, createVlookupOperation()],
                    }))
                  }
                >
                  Add VLOOKUP
                </button>
              </div>

              {transformConfig.vlookup_operations.map((operation, operationIndex) => (
                <article key={`vlookup-${operationIndex}`} className="op-card">
                  <div className="op-grid">
                    <label>
                      Mode
                      <select
                        value={operation.lookup_mode}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            lookup_mode: event.target.value,
                          }))
                        }
                      >
                        <option value="exact">Exact</option>
                        <option value="nearest">Nearest</option>
                      </select>
                    </label>
                    <label>
                      Lookup Sheet
                      <select
                        value={operation.lookup_sheet}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            lookup_sheet: event.target.value,
                          }))
                        }
                      >
                        <option value="">Select sheet</option>
                        {sheetNames.map((sheetName) => (
                          <option key={`lookup-sheet-${sheetName}`} value={sheetName}>
                            {sheetName}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Base Key Columns (comma-separated)
                      <input
                        type="text"
                        value={operation.base_key_columns}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            base_key_columns: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label>
                      Lookup Key Columns (comma-separated)
                      <input
                        type="text"
                        value={operation.lookup_key_columns}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            lookup_key_columns: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label>
                      Return Columns (comma-separated)
                      <input
                        type="text"
                        value={operation.return_columns}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            return_columns: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label>
                      Output Prefix
                      <input
                        type="text"
                        value={operation.output_prefix}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            output_prefix: event.target.value,
                          }))
                        }
                      />
                    </label>
                  </div>

                  <button
                    type="button"
                    className="danger"
                    onClick={() =>
                      setTransformConfig((current) => ({
                        ...current,
                        vlookup_operations: current.vlookup_operations.filter(
                          (_, index) => index !== operationIndex
                        ),
                      }))
                    }
                  >
                    Remove VLOOKUP
                  </button>
                </article>
              ))}
            </div>
        </section>

        {builderErrors.length > 0 ? (
          <div className="error-box">
            {builderErrors.map((message) => (
              <p key={message} className="error-item">
                {message}
              </p>
            ))}
          </div>
        ) : null}

        <button onClick={runUploadAutomation} disabled={uploadLoading}>
          {uploadLoading ? 'Running Upload…' : 'Run Upload'}
        </button>

        {uploadError ? <p className="error">{uploadError}</p> : null}
        {transformsApplied ? <p className="success">Transforms applied successfully.</p> : null}

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
                  {resultSheets.includes(sheetName) ? <span className="badge">transformed</span> : null}
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
    </main>
  )
}
