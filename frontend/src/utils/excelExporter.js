import * as XLSX from 'xlsx'

/**
 * NissiGrid Native Excel (.xlsx) Exporter Utility
 * Generates true Microsoft Excel binary spreadsheets (.xlsx) directly in the browser
 */

export function exportTableToExcel({ filename = 'export_table', columns = [], data = [] }) {
  if (!data || data.length === 0) {
    alert('No data available in this table to export.')
    return
  }

  // Map input data rows to custom column headers
  const formattedRows = data.map(row => {
    const rowObj = {}
    columns.forEach(col => {
      const header = typeof col === 'string' ? col : (col.header || col.label || col.key)
      const key = typeof col === 'string' ? col : (col.key || col.accessor || col.field)
      let val = row[key]

      if (val === null || val === undefined) {
        val = ''
      } else if (typeof val === 'boolean') {
        val = val ? 'YES' : 'NO'
      } else if (typeof val === 'object') {
        val = JSON.stringify(val)
      }

      rowObj[header] = val
    })
    return rowObj
  })

  // Create native XLSX worksheet & workbook
  const worksheet = XLSX.utils.json_to_sheet(formattedRows)
  
  // Apply auto-column width formatting
  const colWidths = columns.map(col => {
    const header = typeof col === 'string' ? col : (col.header || col.label || col.key)
    const maxLen = Math.max(header.length, 12)
    return { wch: maxLen + 4 }
  })
  worksheet['!cols'] = colWidths

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Audit Line Items')

  // Generate downloadable .xlsx file
  const safeFilename = filename.toLowerCase().replace(/[^a-z0-9_-]/g, '_')
  XLSX.writeFile(workbook, `${safeFilename}_${new Date().toISOString().slice(0, 10)}.xlsx`)
}
