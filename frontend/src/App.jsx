import { useEffect, useMemo, useState } from 'react'

const envApiBase = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/$/, '')
const isLocalApiBase = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(envApiBase)
const API_BASE = !import.meta.env.DEV && isLocalApiBase ? '' : envApiBase

const createJoinKey = () => ({ base_column: '', source_column: '' })
const createConcatPart = () => ({ sheet: '', column: '', join_keys: [] })
const createConcatOperation = () => ({
  output_column: '',
  delimiter: '',
  parts: [createConcatPart(), createConcatPart()],
})
const createVlookupOperation = () => ({
  lookup_value_column: '',
  table_array_sheet: '',
  table_array_lookup_column: '',
  return_column: '',
  range_lookup: false,
  output_column: '',
  advanced_multi_key: false,
  lookup_mode: 'exact',
  base_key_columns: '',
  lookup_sheet: '',
  lookup_key_columns: '',
  return_columns: '',
  output_prefix: '',
})
const createClassicStickerField = (column = '', label = '') => ({ column, label })
const CLASSIC_STICKER_SIZE_OPTIONS = [
  { value: '2x2', label: '2 x 2 inches' },
  { value: '4x2', label: '4 x 2 inches' },
  { value: '4x4', label: '4 x 4 inches' },
  { value: '4x6', label: '4 x 6 inches' },
]

const parseCsvList = (value) =>
  value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)

const getColIndexNum = (tableColumns, lookupColumn, returnColumn) => {
  if (!lookupColumn || !returnColumn) {
    return null
  }
  const lookupIndex = tableColumns.indexOf(lookupColumn)
  const returnIndex = tableColumns.indexOf(returnColumn)
  if (lookupIndex === -1 || returnIndex === -1 || returnIndex < lookupIndex) {
    return null
  }
  return returnIndex - lookupIndex + 1
}

const getSourceSheetFromTransformed = (sheetName) => {
  if (!sheetName.includes('__transformed')) {
    return sheetName
  }
  return sheetName.split('__transformed')[0]
}

const DELIVERY_PRINT_FIELDS = [
  { key: 'ean_code', label: 'EAN Code', candidates: ['ean_code', 'EAN', 'ean'] },
  { key: 'article_code', label: 'Article Code', candidates: ['article_code', 'Article Code'] },
  { key: 'size', label: 'Size', candidates: ['size', 'Size'] },
  { key: 'qty', label: 'Qty', candidates: ['qty', 'Packed Qty', 'Order Qty'] },
]

const pickFirstMatchingColumn = (columns, candidates) =>
  candidates.find((candidate) => columns.includes(candidate)) ?? ''
const isUnnamedColumn = (value) => /^unnamed[:_]/i.test(String(value || ''))
const dedupeClassicColumns = (columns) => {
  const seen = new Map()
  return columns.map((column, index) => {
    const base = String(column || '').trim() || `unnamed_${index + 1}`
    const count = (seen.get(base) ?? 0) + 1
    seen.set(base, count)
    return count === 1 ? base : `${base}_${count}`
  })
}

export function App() {
  const [selectedFile, setSelectedFile] = useState(null)
  const [featureTab, setFeatureTab] = useState('transform')
  const [transformTab, setTransformTab] = useState('concat')
  const [uploadLoading, setUploadLoading] = useState(false)
  const [concatLoading, setConcatLoading] = useState(false)
  const [vlookupLoading, setVlookupLoading] = useState(false)
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
  const [classicStickerSheet, setClassicStickerSheet] = useState('')
  const [deliverySheet, setDeliverySheet] = useState('')
  const [deliveryFieldMapping, setDeliveryFieldMapping] = useState({
    ean_code: '',
    article_code: '',
    size: '',
    qty: '',
  })
  const [deliveryTableOptions, setDeliveryTableOptions] = useState({
    showHeader: true,
    bordered: true,
    textAlign: 'left',
    fontSize: 10,
    cellPadding: 6,
  })
  const [manualInvoiceNumber, setManualInvoiceNumber] = useState('')
  const [manualPoNumber, setManualPoNumber] = useState('')
  const [labelsPortrait, setLabelsPortrait] = useState(false)
  const [labelsPaddingIn, setLabelsPaddingIn] = useState('0.25')
  const [labelsLoading, setLabelsLoading] = useState(false)
  const [labelsError, setLabelsError] = useState('')
  const [classicStickerFields, setClassicStickerFields] = useState([])
  const [classicStickerLabelSize, setClassicStickerLabelSize] = useState('4x6')
  const [classicStickerPaddingIn, setClassicStickerPaddingIn] = useState('0.1')
  const [classicStickersLoading, setClassicStickersLoading] = useState(false)
  const [classicStickersError, setClassicStickersError] = useState('')

  const sheetNames = useMemo(() => Object.keys(sheetResults), [sheetResults])
  const deliverySheetCandidates = useMemo(
    () => sheetNames.filter((sheetName) => sheetName.includes('__delivery_print')),
    [sheetNames]
  )
  const hasUploadResults = useMemo(() => sheetNames.length > 0, [sheetNames])
  const activeSheetResult = activeSheet ? sheetResults[activeSheet] : undefined
  const classicStickerSheetResult = classicStickerSheet ? sheetResults[classicStickerSheet] : undefined
  const deliverySheetResult = deliverySheet ? sheetResults[deliverySheet] : undefined
  const deliveryAvailableColumns = deliverySheetResult?.columns ?? []
  const classicStickerColumnOptions = useMemo(() => {
    const columns = classicStickerSheetResult?.columns ?? []
    const rows = classicStickerSheetResult?.rows ?? []
    if (columns.length === 0) {
      return []
    }

    const allUnnamed = columns.every((column) => isUnnamedColumn(column))
    const firstRow = rows[0] ?? null
    if (!allUnnamed || !firstRow) {
      return columns.map((column) => ({ value: column, label: column }))
    }

    const headerCandidates = columns.map((column, index) => {
      const value = String(firstRow[column] ?? '').trim()
      return value || `unnamed_${index + 1}`
    })
    const dedupedHeaders = dedupeClassicColumns(headerCandidates)
    return columns.map((column, index) => ({
      value: dedupedHeaders[index],
      label: dedupedHeaders[index],
    }))
  }, [classicStickerSheetResult])
  const classicStickerAvailableColumns = classicStickerColumnOptions.map((option) => option.value)
  const classicStickerConfiguredFields = useMemo(
    () => classicStickerFields.filter((field) => field.column.trim()),
    [classicStickerFields]
  )
  const classicStickerPaddingValue = Number.parseFloat(classicStickerPaddingIn)
  const classicStickerHasValidPadding =
    !Number.isNaN(classicStickerPaddingValue) && classicStickerPaddingValue >= 0
  const classicStickerCanGenerate = Boolean(
    selectedFile &&
      hasUploadResults &&
      classicStickerSheet &&
      classicStickerConfiguredFields.length > 0 &&
      classicStickerHasValidPadding
  )
  const hasCompleteFieldMapping = useMemo(
    () => DELIVERY_PRINT_FIELDS.every((field) => Boolean(deliveryFieldMapping[field.key])),
    [deliveryFieldMapping]
  )

  useEffect(() => {
    if (sheetNames.length === 0) {
      setClassicStickerSheet('')
      setClassicStickerFields([])
      setDeliverySheet('')
      return
    }
    if (!classicStickerSheet || !sheetNames.includes(classicStickerSheet)) {
      setClassicStickerSheet(sheetNames[0])
    }
  }, [sheetNames, classicStickerSheet])

  useEffect(() => {
    if (classicStickerAvailableColumns.length === 0) {
      setClassicStickerFields([])
      return
    }

    setClassicStickerFields((current) => {
      const validCurrent = current.filter(
        (field) => !field.column || classicStickerAvailableColumns.includes(field.column)
      )
      if (validCurrent.length > 0) {
        return validCurrent
      }

      return classicStickerAvailableColumns.map((column) => createClassicStickerField(column, column))
    })
  }, [classicStickerAvailableColumns])

  useEffect(() => {
    if (sheetNames.length === 0) {
      setDeliverySheet('')
      return
    }
    const preferredSheet = deliverySheetCandidates[0] ?? sheetNames[0]
    if (
      deliverySheetCandidates.length > 0 &&
      deliverySheet &&
      !deliverySheet.includes('__delivery_print')
    ) {
      setDeliverySheet(preferredSheet)
      return
    }
    if (!deliverySheet || !sheetNames.includes(deliverySheet)) {
      setDeliverySheet(preferredSheet)
    }
  }, [sheetNames, deliverySheet, deliverySheetCandidates])

  useEffect(() => {
    if (deliveryAvailableColumns.length === 0) {
      setDeliveryFieldMapping({
        ean_code: '',
        article_code: '',
        size: '',
        qty: '',
      })
      return
    }
    setDeliveryFieldMapping((current) => {
      const next = { ...current }
      DELIVERY_PRINT_FIELDS.forEach((field) => {
        const currentSelection = current[field.key]
        if (currentSelection && deliveryAvailableColumns.includes(currentSelection)) {
          next[field.key] = currentSelection
        } else {
          next[field.key] = pickFirstMatchingColumn(deliveryAvailableColumns, field.candidates)
        }
      })
      return next
    })
  }, [deliveryAvailableColumns])

  const columnsBySheet = useMemo(() => {
    const mapping = {}
    Object.entries(sheetResults).forEach(([sheetName, payload]) => {
      mapping[sheetName] = payload.columns ?? []
    })
    return mapping
  }, [sheetResults])

  const baseSheetColumns = columnsBySheet[transformConfig.base_sheet] ?? []
  const concatOutputColumns = useMemo(
    () =>
      transformConfig.concat_operations
        .map((operation) => operation.output_column.trim())
        .filter(Boolean),
    [transformConfig.concat_operations]
  )
  const vlookupLookupValueColumns = useMemo(
    () => [...new Set([...baseSheetColumns, ...concatOutputColumns])],
    [baseSheetColumns, concatOutputColumns]
  )

  const isAnyActionLoading =
    uploadLoading || concatLoading || vlookupLoading || labelsLoading || classicStickersLoading

  const resolveSheetForRequest = (sheetName, errors, contextLabel) => {
    if (!sheetName) {
      return sheetName
    }

    if (sheetNames.includes(sheetName)) {
      const sourceCandidate = getSourceSheetFromTransformed(sheetName)
      if (sourceCandidate !== sheetName && !sheetNames.includes(sourceCandidate)) {
        errors.push(
          `${contextLabel}: transformed sheet '${sheetName}' requires source sheet '${sourceCandidate}' in uploaded file`
        )
      }
      return sourceCandidate
    }

    return sheetName
  }

  const buildConcatOperations = (errors, allowedOutputColumns = null) => {
    const indexedOperations = transformConfig.concat_operations
      .map((operation, operationIndex) => ({ operation, operationIndex }))
      .filter(({ operation }) => {
        if (allowedOutputColumns === null) {
          return true
        }
        return allowedOutputColumns.has(operation.output_column.trim())
      })

    return indexedOperations.map(({ operation, operationIndex }) => {
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

        const isCrossSheet =
          part.sheet && transformConfig.base_sheet && part.sheet !== transformConfig.base_sheet
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
  }

  const buildVlookupOperations = (errors) => {
    return transformConfig.vlookup_operations.map((operation, operationIndex) => {
      if (operation.advanced_multi_key) {
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
          advanced_multi_key: true,
          lookup_mode: operation.lookup_mode,
          base_key_columns: baseKeys,
          lookup_sheet: operation.lookup_sheet,
          lookup_key_columns: lookupKeys,
          return_columns: returnColumns,
          output_prefix: operation.output_prefix,
        }
      }

      if (!operation.lookup_value_column) {
        errors.push(`VLOOKUP operation ${operationIndex + 1}: lookup value column is required`)
      }
      if (!operation.table_array_sheet) {
        errors.push(`VLOOKUP operation ${operationIndex + 1}: table array sheet is required`)
      }
      if (!operation.table_array_lookup_column) {
        errors.push(`VLOOKUP operation ${operationIndex + 1}: table array lookup column is required`)
      }
      if (!operation.return_column) {
        errors.push(`VLOOKUP operation ${operationIndex + 1}: return column is required`)
      }

      const lookupColumns = columnsBySheet[operation.table_array_sheet] ?? []
      const colIndexNum = getColIndexNum(
        lookupColumns,
        operation.table_array_lookup_column,
        operation.return_column
      )
      if (colIndexNum === null) {
        errors.push(
          `VLOOKUP operation ${operationIndex + 1}: return column must be in table_array and to the right of lookup column`
        )
      }

      return {
        lookup_value_column: operation.lookup_value_column,
        table_array_sheet: operation.table_array_sheet,
        table_array_lookup_column: operation.table_array_lookup_column,
        col_index_num: colIndexNum ?? 0,
        range_lookup: operation.range_lookup,
        output_column: operation.output_column || operation.return_column,
      }
    })
  }

  const buildTransformConfigPayload = (mode) => {
    const errors = []
    const selectedVlookupOps = mode === 'vlookup' ? buildVlookupOperations(errors) : []

    let requiredConcatOutputs = null
    if (mode === 'vlookup') {
      const lookupOutputs = new Set(concatOutputColumns)
      requiredConcatOutputs = new Set()

      transformConfig.vlookup_operations.forEach((operation, operationIndex) => {
        if (operation.advanced_multi_key) {
          parseCsvList(operation.base_key_columns).forEach((column) => {
            if (lookupOutputs.has(column)) {
              requiredConcatOutputs.add(column)
            }
          })
          return
        }

        const lookupValueColumn = operation.lookup_value_column.trim()
        if (lookupOutputs.has(lookupValueColumn)) {
          requiredConcatOutputs.add(lookupValueColumn)
        }
      })

      requiredConcatOutputs.forEach((columnName) => {
        const exists = transformConfig.concat_operations.some(
          (operation) => operation.output_column.trim() === columnName
        )
        if (!exists) {
          errors.push(
            `VLOOKUP depends on concat output '${columnName}', but no matching concat operation is configured`
          )
        }
      })
    }

    const selectedConcatOps =
      mode === 'concat'
        ? buildConcatOperations(errors)
        : mode === 'vlookup' && requiredConcatOutputs && requiredConcatOutputs.size > 0
          ? buildConcatOperations(errors, requiredConcatOutputs)
          : []

    if (mode === 'concat' && selectedConcatOps.length === 0) {
      errors.push('Add at least one concat operation before running concat')
    }
    if (mode === 'vlookup' && selectedVlookupOps.length === 0) {
      errors.push('Add at least one VLOOKUP operation before running VLOOKUP')
    }

    const resolvedBaseSheet = resolveSheetForRequest(
      transformConfig.base_sheet,
      errors,
      'Base sheet'
    )
    if (!resolvedBaseSheet && (selectedConcatOps.length > 0 || selectedVlookupOps.length > 0)) {
      errors.push('Base sheet is required when advanced operations are configured')
    }

    if (errors.length > 0) {
      return { payload: null, errors }
    }

    return {
      payload: {
        base_sheet: resolvedBaseSheet,
        concat_operations: selectedConcatOps,
        vlookup_operations: selectedVlookupOps,
      },
      errors: [],
    }
  }

  const runUploadOnly = async () => {
    if (!selectedFile) {
      setUploadError('Please select a file before running upload')
      return
    }

    setUploadLoading(true)
    setUploadError('')
    setBuilderErrors([])
    setTransformsApplied(false)
    setResultSheets([])

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const response = await fetch(`${API_BASE}/api/automate/upload`, {
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
      setResultSheets([])
      setTransformsApplied(false)
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

  const runTransform = async (mode) => {
    if (!selectedFile) {
      setUploadError('Please select a file before running a transform')
      return
    }

    const { payload: transformPayload, errors: configErrors } = buildTransformConfigPayload(mode)
    setBuilderErrors(configErrors)
    if (configErrors.length > 0 || !transformPayload) {
      setUploadError('Please fix transform configuration errors before running')
      return
    }

    if (mode === 'concat') {
      setConcatLoading(true)
    } else {
      setVlookupLoading(true)
    }
    setUploadError('')

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('config', JSON.stringify(transformPayload))

      const response = await fetch(`${API_BASE}/api/automate/upload`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const payload = await response.json()
        throw new Error(payload.detail ?? 'Transform run failed')
      }

      const payload = await response.json()
      const sheets = payload.sheets ?? {}
      const names = Object.keys(sheets)

      setSheetResults(sheets)
      setResultSheets(payload.result_sheets ?? [])
      setTransformsApplied(Boolean(payload.transforms_applied))
      setActiveSheet(names[0] ?? '')
    } catch (err) {
      setUploadError(err.message)
      setSheetResults({})
      setResultSheets([])
      setTransformsApplied(false)
      setActiveSheet('')
    } finally {
      if (mode === 'concat') {
        setConcatLoading(false)
      } else {
        setVlookupLoading(false)
      }
    }
  }

  const generateLabelsPdf = async () => {
    if (!selectedFile) {
      setLabelsError('Select and upload a file first.')
      return
    }

    const padding = Number.parseFloat(labelsPaddingIn)
    if (Number.isNaN(padding) || padding < 0.1 || padding > 0.4) {
      setLabelsError('Padding must be between 0.1 and 0.4 inches.')
      return
    }

    setLabelsLoading(true)
    setLabelsError('')

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('mode', 'labels_pdf')
      formData.append('portrait', labelsPortrait ? 'true' : 'false')
      formData.append('padding_in', String(padding))
      formData.append('manual_invoice_number', manualInvoiceNumber.trim())
      formData.append('manual_po_number', manualPoNumber.trim())
      formData.append('delivery_sheet', deliverySheet)

      const response = await fetch(`${API_BASE}/api/automate/upload`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const contentType = response.headers.get('content-type') ?? ''
        if (contentType.includes('application/json')) {
          const payload = await response.json()
          throw new Error(payload.detail ?? 'Label PDF generation failed')
        }
        throw new Error('Label PDF generation failed')
      }

      const blob = await response.blob()
      const disposition = response.headers.get('content-disposition') ?? ''
      const filenameMatch = disposition.match(/filename="([^"]+)"/i)
      const filename = filenameMatch?.[1] ?? 'PO# labels.pdf'
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      setLabelsError(error.message || 'Label PDF generation failed')
    } finally {
      setLabelsLoading(false)
    }
  }

  const setClassicStickerField = (fieldIndex, updater) => {
    setClassicStickerFields((current) => {
      const next = [...current]
      next[fieldIndex] = updater(next[fieldIndex])
      return next
    })
  }

  const moveClassicStickerField = (fieldIndex, direction) => {
    setClassicStickerFields((current) => {
      const targetIndex = fieldIndex + direction
      if (targetIndex < 0 || targetIndex >= current.length) {
        return current
      }

      const next = [...current]
      const [field] = next.splice(fieldIndex, 1)
      next.splice(targetIndex, 0, field)
      return next
    })
  }

  const buildClassicStickerConfig = () => {
    const padding = Number.parseFloat(classicStickerPaddingIn)
    if (!classicStickerSheet) {
      throw new Error('Select a source sheet for classic stickers.')
    }
    if (!CLASSIC_STICKER_SIZE_OPTIONS.some((option) => option.value === classicStickerLabelSize)) {
      throw new Error('Select a valid classic sticker label size.')
    }
    if (Number.isNaN(padding) || padding < 0) {
      throw new Error('Padding must be 0 or greater.')
    }

    const fields = classicStickerFields
      .map((field) => ({
        column: field.column.trim(),
        label: (field.label || field.column).trim() || field.column.trim(),
      }))
      .filter((field) => field.column)

    if (fields.length === 0) {
      throw new Error('Add at least one sticker field before generating the PDF.')
    }

    return {
      sheet_name: classicStickerSheet,
      label_size: classicStickerLabelSize,
      padding_in: padding,
      fields,
    }
  }

  const getClassicStickerFieldError = (field) => {
    if (!field.column.trim()) {
      return 'Choose a source column.'
    }
    return ''
  }

  const generateClassicStickersPdf = async () => {
    if (!selectedFile) {
      setClassicStickersError('Select and upload a file first.')
      return
    }

    setClassicStickersLoading(true)
    setClassicStickersError('')

    try {
      const classicStickerConfig = buildClassicStickerConfig()
      const formData = new FormData()
      formData.append('file', selectedFile)
      formData.append('mode', 'classic_stickers_pdf')
      formData.append('classic_sticker_config', JSON.stringify(classicStickerConfig))

      const response = await fetch(`${API_BASE}/api/automate/upload`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const contentType = response.headers.get('content-type') ?? ''
        if (contentType.includes('application/json')) {
          const payload = await response.json()
          throw new Error(payload.detail ?? 'Classic sticker PDF generation failed')
        }
        throw new Error('Classic sticker PDF generation failed')
      }

      const blob = await response.blob()
      const disposition = response.headers.get('content-disposition') ?? ''
      const filenameMatch = disposition.match(/filename="([^"]+)"/i)
      const filename = filenameMatch?.[1] ?? 'classic-stickers.pdf'
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      setClassicStickersError(error.message || 'Classic sticker PDF generation failed')
    } finally {
      setClassicStickersLoading(false)
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
        {selectedFile ? (
          <button onClick={runUploadOnly} disabled={isAnyActionLoading}>
            {uploadLoading ? 'Running Upload…' : 'Run Upload'}
          </button>
        ) : null}

        <div className="feature-tabs">
          <button
            type="button"
            className={`transform-tab ${featureTab === 'transform' ? 'active' : ''}`}
            onClick={() => setFeatureTab('transform')}
          >
            Transform Builder
          </button>
          <button
            type="button"
            className={`transform-tab ${featureTab === 'delivery' ? 'active' : ''}`}
            onClick={() => setFeatureTab('delivery')}
          >
            Delivery Sheet Print (4x6)
          </button>
          <button
            type="button"
            className={`transform-tab ${featureTab === 'classic_stickers' ? 'active' : ''}`}
            onClick={() => setFeatureTab('classic_stickers')}
          >
            Classic Themes Stickers
          </button>
        </div>

        {featureTab === 'transform' ? (
          <>
            <section className="builder-section">
          <h3>Advanced Transform Builder</h3>
          <p className="hint">
            Configure concat and VLOOKUP pipeline. Run Upload first to load sheet and column
            metadata from the selected file.
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

          <div className="transform-tabs">
            <button
              type="button"
              className={`transform-tab ${transformTab === 'concat' ? 'active' : ''}`}
              onClick={() => setTransformTab('concat')}
            >
              Concat
            </button>
            <button
              type="button"
              className={`transform-tab ${transformTab === 'vlookup' ? 'active' : ''}`}
              onClick={() => setTransformTab('vlookup')}
            >
              VLOOKUP
            </button>
          </div>

          {transformTab === 'concat' ? (
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
                                  setConcatPart(operationIndex, partIndex, (current) => {
                                    const nextSheet = event.target.value
                                    const isSameAsBase =
                                      Boolean(nextSheet) &&
                                      Boolean(transformConfig.base_sheet) &&
                                      nextSheet === transformConfig.base_sheet
                                    return {
                                      ...current,
                                      sheet: nextSheet,
                                      join_keys: isSameAsBase ? [] : current.join_keys,
                                    }
                                  })
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
                          ) : (
                            <p className="hint">Join keys are only needed for cross-sheet concat.</p>
                          )}

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

              <button onClick={() => runTransform('concat')} disabled={isAnyActionLoading || !selectedFile}>
                {concatLoading ? 'Running Concat…' : 'Run Concat'}
              </button>
            </div>
          ) : (
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

              <p className="hint">
                Mapping: lookup_value = selected base-sheet column, table_array = selected lookup
                sheet (starting from lookup column), col_index_num = auto-computed from return
                column, range_lookup = FALSE exact or TRUE approximate. Concat output columns are
                available as lookup_value when concat operations are configured.
              </p>

              {transformConfig.vlookup_operations.map((operation, operationIndex) => (
                <article key={`vlookup-${operationIndex}`} className="op-card">
                  <p className="hint">
                    VLOOKUP(lookup_value, table_array, col_index_num, [range_lookup])
                  </p>
                  <div className="op-grid">
                    <label>
                      Lookup Value Column
                      <select
                        value={operation.lookup_value_column}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            lookup_value_column: event.target.value,
                          }))
                        }
                      >
                        <option value="">Select base/concat column</option>
                        {vlookupLookupValueColumns.map((column) => (
                          <option key={`lookup-value-${column}`} value={column}>
                            {column}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Table Array Sheet
                      <select
                        value={operation.table_array_sheet}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            table_array_sheet: event.target.value,
                            table_array_lookup_column: '',
                            return_column: '',
                          }))
                        }
                      >
                        <option value="">Select sheet</option>
                        {sheetNames.map((sheetName) => (
                          <option key={`table-array-sheet-${sheetName}`} value={sheetName}>
                            {sheetName}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Table Array Lookup Column
                      <select
                        value={operation.table_array_lookup_column}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            table_array_lookup_column: event.target.value,
                          }))
                        }
                      >
                        <option value="">Select lookup column</option>
                        {(columnsBySheet[operation.table_array_sheet] ?? []).map((column) => (
                          <option key={`table-lookup-col-${column}`} value={column}>
                            {column}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Return Column
                      <select
                        value={operation.return_column}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            return_column: event.target.value,
                          }))
                        }
                      >
                        <option value="">Select return column</option>
                        {(columnsBySheet[operation.table_array_sheet] ?? []).map((column) => (
                          <option key={`return-col-${column}`} value={column}>
                            {column}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      col_index_num (auto)
                      <input
                        type="text"
                        value={String(
                          getColIndexNum(
                            columnsBySheet[operation.table_array_sheet] ?? [],
                            operation.table_array_lookup_column,
                            operation.return_column
                          ) ?? ''
                        )}
                        readOnly
                      />
                    </label>
                    <label>
                      range_lookup
                      <select
                        value={operation.range_lookup ? 'true' : 'false'}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            range_lookup: event.target.value === 'true',
                          }))
                        }
                      >
                        <option value="false">FALSE (Exact match)</option>
                        <option value="true">TRUE (Approximate match)</option>
                      </select>
                    </label>
                    <label>
                      Output Column Name
                      <input
                        type="text"
                        value={operation.output_column}
                        onChange={(event) =>
                          setVlookupOperation(operationIndex, (current) => ({
                            ...current,
                            output_column: event.target.value,
                          }))
                        }
                      />
                    </label>
                  </div>

                  <label className="toggle">
                    <input
                      type="checkbox"
                      checked={operation.advanced_multi_key}
                      onChange={(event) =>
                        setVlookupOperation(operationIndex, (current) => ({
                          ...current,
                          advanced_multi_key: event.target.checked,
                        }))
                      }
                    />
                    Use advanced legacy matching
                  </label>

                  {operation.advanced_multi_key ? (
                    <div className="op-grid">
                      <label>
                        Legacy Mode
                        <select
                          value={operation.lookup_mode}
                          onChange={(event) =>
                            setVlookupOperation(operationIndex, (current) => ({
                              ...current,
                              lookup_mode: event.target.value,
                            }))
                          }
                        >
                          <option value="exact">exact</option>
                          <option value="nearest">nearest (advanced)</option>
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
                            <option key={`legacy-lookup-sheet-${sheetName}`} value={sheetName}>
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
                  ) : null}

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

              <button onClick={() => runTransform('vlookup')} disabled={isAnyActionLoading || !selectedFile}>
                {vlookupLoading ? 'Running VLOOKUP…' : 'Run VLOOKUP'}
              </button>
            </div>
          )}
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
          </>
        ) : featureTab === 'delivery' ? (
          <section className="builder-section">
            <h3>Delivery Sheet Print</h3>
            <p className="hint">
              Print order data as a 4x6 inch table. Select a sheet and columns, then print.
            </p>

            {hasUploadResults ? (
              <>
                <div className="op-grid">
                  <label>
                    Order Sheet
                    <select
                      value={deliverySheet}
                      onChange={(event) => setDeliverySheet(event.target.value)}
                    >
                      <option value="">Select sheet</option>
                      {sheetNames.map((sheetName) => (
                        <option key={`delivery-sheet-${sheetName}`} value={sheetName}>
                          {sheetName}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <h4>Field Mapping</h4>
                <div className="op-grid delivery-mapping-grid">
                  {DELIVERY_PRINT_FIELDS.map((field) => (
                    <label key={`field-map-${field.key}`}>
                      {field.label}
                      <select
                        value={deliveryFieldMapping[field.key]}
                        onChange={(event) =>
                          setDeliveryFieldMapping((current) => ({
                            ...current,
                            [field.key]: event.target.value,
                          }))
                        }
                      >
                        <option value="">Select source column</option>
                        {deliveryAvailableColumns.map((column) => (
                          <option key={`field-option-${field.key}-${column}`} value={column}>
                            {column}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>

                <div className="op-grid delivery-controls-grid">
                  <label>
                    Header Row
                    <select
                      value={deliveryTableOptions.showHeader ? 'show' : 'hide'}
                      onChange={(event) =>
                        setDeliveryTableOptions((current) => ({
                          ...current,
                          showHeader: event.target.value === 'show',
                        }))
                      }
                    >
                      <option value="show">Show</option>
                      <option value="hide">Hide</option>
                    </select>
                  </label>
                  <label>
                    Borders
                    <select
                      value={deliveryTableOptions.bordered ? 'on' : 'off'}
                      onChange={(event) =>
                        setDeliveryTableOptions((current) => ({
                          ...current,
                          bordered: event.target.value === 'on',
                        }))
                      }
                    >
                      <option value="on">On</option>
                      <option value="off">Off</option>
                    </select>
                  </label>
                  <label>
                    Text Align
                    <select
                      value={deliveryTableOptions.textAlign}
                      onChange={(event) =>
                        setDeliveryTableOptions((current) => ({
                          ...current,
                          textAlign: event.target.value,
                        }))
                      }
                    >
                      <option value="left">Left</option>
                      <option value="center">Center</option>
                      <option value="right">Right</option>
                    </select>
                  </label>
                  <label>
                    Manual PO Number
                    <input
                      type="text"
                      value={manualPoNumber}
                      onChange={(event) => setManualPoNumber(event.target.value)}
                      placeholder="Optional override"
                    />
                  </label>
                  <label>
                    Manual Invoice Number
                    <input
                      type="text"
                      value={manualInvoiceNumber}
                      onChange={(event) => setManualInvoiceNumber(event.target.value)}
                      placeholder="Optional override"
                    />
                  </label>
                  <label>
                    Font Size (px)
                    <input
                      type="number"
                      min="7"
                      max="18"
                      value={deliveryTableOptions.fontSize}
                      onChange={(event) => {
                        const nextValue = Number.parseInt(event.target.value, 10)
                        setDeliveryTableOptions((current) => ({
                          ...current,
                          fontSize: Number.isNaN(nextValue) ? 10 : nextValue,
                        }))
                      }}
                    />
                  </label>
                  <label>
                    Cell Padding (px)
                    <input
                      type="number"
                      min="2"
                      max="16"
                      value={deliveryTableOptions.cellPadding}
                      onChange={(event) => {
                        const nextValue = Number.parseInt(event.target.value, 10)
                        setDeliveryTableOptions((current) => ({
                          ...current,
                          cellPadding: Number.isNaN(nextValue) ? 6 : nextValue,
                        }))
                      }}
                    />
                  </label>
                </div>

                {!hasCompleteFieldMapping ? (
                  <p className="error">Map all required fields before generating labels.</p>
                ) : null}

                <section className="builder-section">
                  <h4>4x6 Label Stickers</h4>
                  <p className="hint">
                    Generate print-ready label PDF using the same Delivery Sheet selection and invoice override above.
                  </p>
                  <div className="op-grid label-pdf-controls">
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={labelsPortrait}
                        onChange={(event) => setLabelsPortrait(event.target.checked)}
                      />
                      Portrait (4x6)
                    </label>
                    <label>
                      Padding (inches)
                      <input
                        type="number"
                        min="0.1"
                        max="0.4"
                        step="0.01"
                        value={labelsPaddingIn}
                        onChange={(event) => setLabelsPaddingIn(event.target.value)}
                      />
                    </label>
                  </div>
                  <button
                    type="button"
                    onClick={generateLabelsPdf}
                    disabled={!selectedFile || labelsLoading}
                  >
                    {labelsLoading ? 'Generating Labels PDF…' : 'Generate 4x6 Labels PDF'}
                  </button>
                  {labelsError ? <p className="error">{labelsError}</p> : null}
                </section>
              </>
            ) : (
              <p className="hint">Run upload first to load order sheets and rows for printing.</p>
            )}
          </section>
        ) : (
          <section className="builder-section">
            <h3>Classic Themes Stickers</h3>
            <p className="hint">
              Generate classic field-value sticker PDFs from any uploaded sheet.
            </p>
            <p className="hint">There is no fixed number of fields. Choose as many columns as you need.</p>

            {hasUploadResults ? (
              <>
                <div className="op-grid">
                  <label>
                    Source Sheet
                    <select
                      value={classicStickerSheet}
                      onChange={(event) => setClassicStickerSheet(event.target.value)}
                    >
                      <option value="">Select sheet</option>
                      {sheetNames.map((sheetName) => (
                        <option key={`classic-sheet-${sheetName}`} value={sheetName}>
                          {sheetName}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Label Size
                    <select
                      value={classicStickerLabelSize}
                      onChange={(event) => setClassicStickerLabelSize(event.target.value)}
                    >
                      {CLASSIC_STICKER_SIZE_OPTIONS.map((option) => (
                        <option key={`classic-size-${option.value}`} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {!classicStickerSheet ? (
                    <p className="error">Choose a source sheet to configure sticker fields.</p>
                  ) : null}
                  <label>
                    Padding (inches)
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={classicStickerPaddingIn}
                      onChange={(event) => setClassicStickerPaddingIn(event.target.value)}
                    />
                  </label>
                  {!classicStickerHasValidPadding ? (
                    <p className="error">Padding must be 0 or greater.</p>
                  ) : null}
                </div>

                <div className="op-card classic-stickers-placeholder">
                  <div className="builder-header">
                    <h4>Sticker Fields</h4>
                    <button
                      type="button"
                      onClick={() =>
                        setClassicStickerFields((current) => [...current, createClassicStickerField()])
                      }
                    >
                      Add Custom Field
                    </button>
                  </div>
                  <p className="hint">
                    Choose columns in the order they should print as `LABEL : VALUE` lines.
                  </p>
                  {classicStickerAvailableColumns.length > 0 ? (
                    <p className="hint">
                      Available columns: {classicStickerAvailableColumns.join(', ')}
                    </p>
                  ) : null}

                  {!classicStickerSheet ? (
                    <p className="hint">Pick a source sheet first to load available columns.</p>
                  ) : classicStickerFields.length > 0 ? (
                    <div className="classic-sticker-fields">
                      {classicStickerFields.map((field, fieldIndex) => (
                        <div key={`classic-field-${fieldIndex}`} className="classic-sticker-field-row">
                          <label>
                            Source Column
                            <select
                              value={field.column}
                              onChange={(event) =>
                                setClassicStickerField(fieldIndex, (current) => ({
                                  ...current,
                                  column: event.target.value,
                                  label: current.label || event.target.value,
                                }))
                              }
                            >
                              <option value="">Select column</option>
                              {classicStickerColumnOptions.map((option) => (
                                <option
                                  key={`classic-field-column-${fieldIndex}-${option.value}`}
                                  value={option.value}
                                >
                                  {option.label}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Display Label
                            <input
                              type="text"
                              value={field.label}
                              onChange={(event) =>
                                setClassicStickerField(fieldIndex, (current) => ({
                                  ...current,
                                  label: event.target.value,
                                }))
                              }
                              placeholder={field.column || 'Uses column name'}
                            />
                          </label>
                          <div className="classic-sticker-row-actions">
                            <button
                              type="button"
                              onClick={() => moveClassicStickerField(fieldIndex, -1)}
                              disabled={fieldIndex === 0}
                            >
                              Move Up
                            </button>
                            <button
                              type="button"
                              onClick={() => moveClassicStickerField(fieldIndex, 1)}
                              disabled={fieldIndex === classicStickerFields.length - 1}
                            >
                              Move Down
                            </button>
                            <button
                              type="button"
                              className="danger"
                              onClick={() =>
                                setClassicStickerFields((current) =>
                                  current.filter((_, index) => index !== fieldIndex)
                                )
                              }
                            >
                              Remove
                            </button>
                          </div>
                          {getClassicStickerFieldError(field) ? (
                            <p className="error classic-sticker-inline-error">
                              {getClassicStickerFieldError(field)}
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="hint">
                      No fields added yet. Use `Add Custom Field` to create a blank field row.
                    </p>
                  )}
                </div>

                {classicStickerCanGenerate ? (
                  <p className="hint">
                    Will generate one sticker per row from sheet {classicStickerSheet} using{' '}
                    {classicStickerConfiguredFields.length} fields at size {classicStickerLabelSize}.
                  </p>
                ) : (
                  <p className="hint">
                    Finish the sheet, field, and padding setup to enable PDF generation.
                  </p>
                )}

                <button
                  type="button"
                  onClick={generateClassicStickersPdf}
                  disabled={!classicStickerCanGenerate || classicStickersLoading}
                >
                  {classicStickersLoading
                    ? 'Generating Classic Stickers PDF…'
                    : 'Generate Classic Stickers PDF'}
                </button>
                {classicStickersError ? <p className="error">{classicStickersError}</p> : null}
              </>
            ) : (
              <p className="hint">
                Run upload first to load sheets and columns before configuring classic sticker PDFs.
              </p>
            )}
          </section>
        )}
      </section>
    </main>
  )
}
