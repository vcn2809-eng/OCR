import React from 'react'

export default function DataTable({
  columns = [],
  data = [],
  loading = false,
  emptyMessage = 'No records found.',
  onRowClick = null,
}) {
  if (loading) {
    return (
      <div className="card" style={{ padding: 48, textAlign: 'center' }}>
        <div className="spinner" style={{ margin: 'auto' }} />
        <div style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: 13 }}>Loading table data...</div>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="card" style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: 'rgba(0, 212, 255, 0.06)', borderBottom: '1px solid var(--border)', textAlign: 'left' }}>
              {columns.map((col, idx) => (
                <th
                  key={idx}
                  style={{
                    padding: '12px 16px',
                    fontSize: 11,
                    fontWeight: 700,
                    color: col.color || 'var(--cyan)',
                    textAlign: col.align || 'left',
                    width: col.width || 'auto',
                  }}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, rowIdx) => (
              <tr
                key={row.id || row.document_id || row.vendor_id || rowIdx}
                onClick={() => onRowClick && onRowClick(row)}
                style={{
                  borderBottom: '1px solid var(--border)',
                  background: rowIdx % 2 === 0 ? 'rgba(255, 255, 255, 0.01)' : 'transparent',
                  cursor: onRowClick ? 'pointer' : 'default',
                }}
              >
                {columns.map((col, colIdx) => (
                  <td
                    key={colIdx}
                    style={{
                      padding: '12px 16px',
                      textAlign: col.align || 'left',
                      color: col.textColor || 'inherit',
                    }}
                  >
                    {col.cell ? col.cell(row, rowIdx) : row[col.accessor]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
