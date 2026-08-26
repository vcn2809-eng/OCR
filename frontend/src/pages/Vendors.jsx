import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Building2, Plus, RefreshCw, FileText, ChevronRight } from 'lucide-react'
import api from '../api/client.js'
import { useToast } from '../ToastContext.jsx'
import DataTable from '../components/DataTable.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

export default function VendorsPage() {
  const [vendors, setVendors] = useState([])
  const [selectedVendor, setSelectedVendor] = useState(null)
  const [vendorDetail, setVendorDetail] = useState(null)
  const [linkedDocs, setLinkedDocs] = useState([])

  const [selectedDocId, setSelectedDocId] = useState(null)
  const [extractedRows, setExtractedRows] = useState([])
  const [loadingRows, setLoadingRows] = useState(false)
  const [rowsSearchQuery, setRowsSearchQuery] = useState('')
  const [searchColumn, setSearchColumn] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [rowsPage, setRowsPage] = useState(1)
  const [rowsPerPage, setRowsPerPage] = useState(9999)

  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState(null)

  // Add Vendor Form
  const [showAdd, setShowAdd] = useState(false)
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const toast = useToast()

  const loadVendors = useCallback(async () => {
    setLoadingList(true)
    setError(null)
    try {
      const data = await api.listVendors()
      setVendors(data || [])
    } catch (e) {
      setError(e.message)
      toast(e.message, 'error')
    } finally {
      setLoadingList(false)
    }
  }, [toast])

  useEffect(() => { loadVendors() }, [loadVendors])

  const handleSelectDocument = (docId) => {
    setSelectedDocId(docId)
    setRowsSearchQuery('')
    setSearchColumn('')
    setRowsPage(1)
  }

  // Debounce search query
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQuery(rowsSearchQuery)
    }, 300)
    return () => clearTimeout(handler)
  }, [rowsSearchQuery])

  // Fetch rows from backend when selectedDocId, debouncedQuery, or searchColumn changes
  useEffect(() => {
    if (!selectedDocId) return

    let active = true
    const fetchRows = async () => {
      setLoadingRows(true)
      try {
        const rows = await api.getDocumentRows(selectedDocId, debouncedQuery, searchColumn)
        if (active) {
          setExtractedRows(rows || [])
          setRowsPage(1)
        }
      } catch (e) {
        if (active) {
          toast(`Failed to load document items: ${e.message}`, 'error')
        }
      } finally {
        if (active) {
          setLoadingRows(false)
        }
      }
    }

    fetchRows()
    return () => {
      active = false
    }
  }, [selectedDocId, debouncedQuery, searchColumn, toast])

  const handleSelectVendor = async (v) => {
    setSelectedVendor(v)
    setLoadingDetail(true)
    setExtractedRows([])
    setSelectedDocId(null)
    try {
      const detail = await api.getVendorById(v.vendor_id)
      setVendorDetail(detail)

      // Fetch documents linked to this vendor
      const docRes = await api.listDocuments({ vendor_id: v.vendor_id })
      const docs = docRes.items || []
      setLinkedDocs(docs)

      if (docs.length > 0) {
        handleSelectDocument(docs[0].document_id)
      }
    } catch (e) {
      toast(`Failed to load vendor details: ${e.message}`, 'error')
    } finally {
      setLoadingDetail(false)
    }
  }

  const handleAddVendorSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return

    setSubmitting(true)
    try {
      const res = await api.saveVendor(name.trim(), address.trim())
      toast(`Vendor "${name}" saved successfully!`, 'success')
      setName('')
      setAddress('')
      setShowAdd(false)
      await loadVendors()
      handleSelectVendor({ vendor_id: res.vendor_id, vendor_name: name.trim() })
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const columns = [
    {
      header: 'Vendor Name',
      accessor: 'vendor_name',
      cell: (row) => (
        <span style={{ fontWeight: 600, color: 'var(--cyan)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Building2 size={15} /> {row.vendor_name}
        </span>
      ),
    },
    {
      header: 'Vendor ID',
      accessor: 'vendor_id',
      cell: (row) => <code style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)' }}>{row.vendor_id}</code>,
    },
    {
      header: 'Action',
      align: 'right',
      cell: (row) => (
        <span style={{ color: 'var(--cyan)', fontSize: 12, display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end' }}>
          View Details <ChevronRight size={13} />
        </span>
      ),
    },
  ]

  // Filter and paginate extracted rows
  const cleanVal = (val) => {
    if (val === null || val === undefined) return ''
    let s = String(val).trim()
    
    // Auto-correct common OCR unit transcription exceptions
    s = s.replace(/\b[BS5]OO\s*(ML|GM|G|L|ml|gm|g|l)\b/g, (match, unit) => '500' + unit)
    s = s.replace(/\b[BS5]0O\s*(ML|GM|G|L|ml|gm|g|l)\b/g, (match, unit) => '500' + unit)
    s = s.replace(/\b[BS5]O0\s*(ML|GM|G|L|ml|gm|g|l)\b/g, (match, unit) => '500' + unit)
    s = s.replace(/\b1OO\s*(ML|GM|G|L|ml|gm|g|l|Gms|gms)\b/g, (match, unit) => '100' + unit)
    s = s.replace(/^_(S|5)OOGM$/i, '500GM')
    s = s.replace(/^_(S|5)00GM$/i, '500GM')
    
    return s
  }

  const cleanNumeric = (val) => {
    if (val === null || val === undefined) return ''
    let s = String(val).trim()
    s = s.replace(/^[^\d.\-,(]+/, '')
    s = s.replace(/[^\d.,%]+$/, '')
    return s
  }

  const SEPARATOR_RE = /^[|{}\[\]\-.~,;:]+$/
  const CATALOG_CODE_RE = /^\d{4,}-\S+/

  const getDescription = (row) => {
    const sortedKeys = Object.keys(row)
      .filter(k => k.startsWith('col_'))
      .sort((a, b) => Number(a.split('_')[1]) - Number(b.split('_')[1]))

    const BRANDS = ['SRL', 'LOBA', 'MERCK', 'CDH', 'NICE']
    const BLACKLIST = ['PAN', 'GSTIN', 'GST', 'MSME', 'UDYAM', 'AASCAQSO0A', 'CODE', 'PRICE', 'LIST', 'PAGE', 'NO.']
    const tokens = []
    
    for (const key of sortedKeys) {
      const val = cleanVal(row[key])
      if (!val) continue
      
      if (SEPARATOR_RE.test(val)) continue
      if (CATALOG_CODE_RE.test(val)) continue
      
      const upper = val.toUpperCase()
      if (BLACKLIST.some(b => upper === b || upper.includes(b))) continue
      if (BRANDS.some(b => upper.includes(b))) continue
      if (/^\b\d*[A-Z]{1,4}\s*(ml|gm|gms|g|l|each)\b/i.test(val) || 
          /^\b[BS5]OO\s*(ML|GM|G|L)\b/i.test(val) || 
          /^(500GM|500ml|25GM|500Gms|5OOGM|BOOML|SOOML|Each|1 Each)$/i.test(val)) continue
          
      const cleanNum = val.replace(/[^\d.\-,()]/g, '')
      if (cleanNum && !isNaN(Number(cleanNum))) continue
      
      tokens.push(val)
    }
    
    return tokens.join(' ').trim()
  }

  const getItemCode = (row) => {
    for (const val of Object.values(row)) {
      const s = cleanVal(val)
      if (CATALOG_CODE_RE.test(s)) {
        return s
      }
    }
    return ''
  }

  const isCatalogItemRow = (row) => {
    return Object.values(row).some(val => CATALOG_CODE_RE.test(cleanVal(val)))
  }

  const isChemicalCatalog = extractedRows.some(r => r.col_11 || r.col_6 || isCatalogItemRow(r))

  const processedRows = isChemicalCatalog ? extractedRows.filter(isCatalogItemRow) : extractedRows

  const filteredRows = processedRows.filter(row => {
    if (!rowsSearchQuery) return true
    const q = rowsSearchQuery.toLowerCase()
    
    if (isChemicalCatalog) {
      const searchStr = [
        row.col_1,
        getDescription(row),
        row.col_48,
        row.col_66,
        row.col_71,
        row.col_14,
        row.col_24,
        row.col_26,
        row.col_35,
      ].filter(Boolean).join(' ').toLowerCase()
      return searchStr.includes(q)
    } else {
      return Object.values(row).some(val => String(val).toLowerCase().includes(q))
    }
  })

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / rowsPerPage))
  const paginatedRows = filteredRows.slice((rowsPage - 1) * rowsPerPage, rowsPage * rowsPerPage)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>Vendors Directory</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
            {vendors.length} registered vendors with linked document tracking
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary btn-sm" onClick={() => setShowAdd(s => !s)}>
            <Plus size={14} /> Add Vendor
          </button>
          <button className="btn btn-secondary btn-sm" onClick={loadVendors}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {/* Add Vendor Form */}
      {showAdd && (
        <div className="card mb-4" style={{ background: 'rgba(0, 212, 255, 0.04)', border: '1px solid rgba(0, 212, 255, 0.2)' }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 12px 0', color: 'var(--cyan)' }}>Add New Vendor</h3>
          <form onSubmit={handleAddVendorSubmit} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 12, alignItems: 'end' }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#aaa', marginBottom: 4 }}>Vendor Name *</label>
              <input className="input" placeholder="e.g. SRL Chemicals" value={name} onChange={e => setName(e.target.value)} required style={{ width: '100%' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#aaa', marginBottom: 4 }}>Address</label>
              <input className="input" placeholder="e.g. Mumbai, MH" value={address} onChange={e => setAddress(e.target.value)} style={{ width: '100%' }} />
            </div>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Saving...' : 'Save Vendor'}
            </button>
          </form>
        </div>
      )}

      {/* Explicit Error State */}
      {error && (
        <div style={{ background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', borderRadius: 8, padding: 14, color: '#f43f5e', fontSize: 13, marginBottom: 16 }}>
          ⚠ {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Vendors List Table */}
        <div>
          <h3 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 10px 0', color: '#ccc' }}>Vendor List</h3>
          <DataTable
            columns={columns}
            data={vendors}
            loading={loadingList}
            emptyMessage="No vendors registered."
            onRowClick={handleSelectVendor}
          />
        </div>

        {/* Selected Vendor Detail & Linked Documents */}
        <div>
          <h3 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 10px 0', color: '#ccc' }}>Selected Vendor Details</h3>
          {loadingDetail ? (
            <div className="card" style={{ padding: 32, textAlign: 'center' }}><div className="spinner" style={{ margin: 'auto' }} /></div>
          ) : vendorDetail ? (
            <div>
              <div className="card mb-3" style={{ background: 'rgba(0, 212, 255, 0.05)', border: '1px solid rgba(0, 212, 255, 0.25)' }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: '#fff', marginBottom: 6 }}>{vendorDetail.vendor_name}</div>
                <div style={{ fontSize: 13, color: '#ccc', marginBottom: 10 }}>📍 {vendorDetail.address || 'No address registered'}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Created: {vendorDetail.created_at ? new Date(vendorDetail.created_at).toLocaleString() : '—'}</div>
              </div>

              {/* Linked Documents List */}
              <div className="card" style={{ padding: 16 }}>
                <h4 style={{ fontSize: 13, fontWeight: 700, margin: '0 0 10px 0', color: 'var(--cyan)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <FileText size={14} /> Linked Documents ({linkedDocs.length})
                </h4>

                {linkedDocs.length === 0 ? (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>No documents linked to this vendor.</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {linkedDocs.map(doc => {
                      const isActive = doc.document_id === selectedDocId
                      return (
                        <div
                          key={doc.document_id}
                          onClick={() => handleSelectDocument(doc.document_id)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            background: isActive ? 'var(--cyan-dim)' : 'rgba(255,255,255,0.02)',
                            padding: '8px 12px',
                            borderRadius: 6,
                            border: isActive ? '1px solid var(--cyan)' : '1px solid var(--border)',
                            cursor: 'pointer',
                            transition: 'all 0.2s'
                          }}
                        >
                          <div>
                            <div style={{ color: isActive ? 'var(--cyan)' : '#fff', fontWeight: 600, fontSize: 13 }}>
                              {doc.original_filename}
                            </div>
                            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Type: {doc.document_type || 'generic'}</div>
                          </div>
                          <StatusBadge status={doc.status} />
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="card" style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>
              Click a vendor from the list to view full details and linked documents.
            </div>
          )}
        </div>
      </div>

      {/* Extracted Catalog Items Table Display */}
      {selectedVendor && selectedDocId && (
        <div className="card mt-4" style={{ padding: 20 }}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 800, color: 'var(--cyan)', margin: 0 }}>
                Extracted Catalog Table Preview
              </h3>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                Showing items for document: <code style={{ color: '#fff', fontFamily: 'monospace' }}>{selectedDocId}</code>
              </p>
            </div>
            <div className="flex items-center gap-2" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Show:</span>
              <select
                className="input"
                value={rowsPerPage}
                onChange={e => {
                  setRowsPerPage(Number(e.target.value))
                  setRowsPage(1)
                }}
                style={{ width: 85, height: 38, padding: '0 10px', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border)', borderRadius: 4, color: '#fff' }}
              >
                <option value={12}>12 rows</option>
                <option value={25}>25 rows</option>
                <option value={50}>50 rows</option>
                <option value={100}>100 rows</option>
                <option value={9999}>All rows</option>
              </select>

              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Column:</span>
              <select
                className="input"
                value={searchColumn}
                onChange={e => {
                  setSearchColumn(e.target.value)
                  setRowsPage(1)
                }}
                style={{ width: 140, height: 38, padding: '0 10px', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border)', borderRadius: 4, color: '#fff' }}
              >
                <option value="">All Columns</option>
                {isChemicalCatalog ? (
                  <>
                    <option value="col_1">Item Code</option>
                    <option value="col_47">Description</option>
                    <option value="col_48">Brand</option>
                    <option value="col_66">Packing</option>
                    <option value="col_71">Qty</option>
                    <option value="col_14">Rate</option>
                    <option value="col_24">Disc %</option>
                    <option value="col_26">Taxable</option>
                    <option value="col_35">Final Value</option>
                  </>
                ) : (
                  extractedRows.length > 0 &&
                  Object.keys(extractedRows[0])
                    .filter(k => k !== 'document_id' && k !== '_normalization_warnings')
                    .map(key => (
                      <option key={key} value={key}>
                        {key.replace(/_/g, ' ').toUpperCase()}
                      </option>
                    ))
                )}
              </select>

              <input
                className="input"
                placeholder="Search catalog items..."
                value={rowsSearchQuery}
                onChange={e => {
                  setRowsSearchQuery(e.target.value)
                  setRowsPage(1)
                }}
                style={{ width: 220 }}
              />
            </div>
          </div>

          {loadingRows ? (
            <div style={{ padding: 48, textAlign: 'center' }}><div className="spinner" style={{ margin: 'auto' }} /></div>
          ) : paginatedRows.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)' }}>No catalog items found.</div>
          ) : (
            <div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)', textAlign: 'left', color: 'var(--cyan)' }}>
                      <th style={{ padding: '10px 8px' }}>#</th>
                      {isChemicalCatalog ? (
                        <>
                          <th style={{ padding: '10px 8px' }}>Item Code</th>
                          <th style={{ padding: '10px 8px' }}>Description</th>
                          <th style={{ padding: '10px 8px' }}>Brand</th>
                          <th style={{ padding: '10px 8px' }}>Packing</th>
                          <th style={{ padding: '10px 8px' }}>Qty</th>
                          <th style={{ padding: '10px 8px' }}>Rate (₹)</th>
                          <th style={{ padding: '10px 8px' }}>Disc %</th>
                          <th style={{ padding: '10px 8px' }}>Taxable (₹)</th>
                          <th style={{ padding: '10px 8px' }}>Final Value (₹)</th>
                        </>
                      ) : (
                        Object.keys(paginatedRows[0])
                          .filter(k => k !== 'document_id' && k !== '_normalization_warnings')
                          .map(key => (
                            <th key={key} style={{ padding: '10px 8px' }}>
                              {key.replace(/_/g, ' ').toUpperCase()}
                            </th>
                          ))
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedRows.map((row, rIdx) => {
                      const serialNum = (rowsPage - 1) * rowsPerPage + rIdx + 1
                      return (
                        <tr key={rIdx} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', hover: { background: 'rgba(255,255,255,0.01)' } }}>
                          <td style={{ padding: '10px 8px', color: 'var(--text-muted)' }}>{serialNum}</td>
                          {isChemicalCatalog ? (
                            <>
                              <td style={{ padding: '10px 8px', fontFamily: 'monospace', color: 'var(--cyan)' }}>
                                {getItemCode(row)}
                              </td>
                              <td style={{ padding: '10px 8px', fontWeight: 500, color: '#fff' }}>
                                {getDescription(row)}
                              </td>
                              <td style={{ padding: '10px 8px' }}>{cleanVal(row.col_48) || '—'}</td>
                              <td style={{ padding: '10px 8px' }}>{cleanVal(row.col_66) || '—'}</td>
                              <td style={{ padding: '10px 8px' }}>{cleanNumeric(row.col_71) || '—'}</td>
                              <td style={{ padding: '10px 8px', fontFamily: 'monospace' }}>{cleanNumeric(row.col_14) || '—'}</td>
                              <td style={{ padding: '10px 8px', color: 'var(--amber)' }}>{cleanNumeric(row.col_24) || '—'}</td>
                              <td style={{ padding: '10px 8px', fontFamily: 'monospace' }}>{cleanNumeric(row.col_26) || '—'}</td>
                              <td style={{ padding: '10px 8px', fontFamily: 'monospace', fontWeight: 600, color: 'var(--green)' }}>
                                {cleanNumeric(row.col_35) || '—'}
                              </td>
                            </>
                          ) : (
                            Object.entries(row)
                              .filter(([k]) => k !== 'document_id' && k !== '_normalization_warnings')
                              .map(([_, val], cIdx) => (
                                <td key={cIdx} style={{ padding: '10px 8px' }}>
                                  {cleanVal(val)}
                                </td>
                              ))
                          )}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/* Table Pagination */}
              <div className="pagination mt-4">
                <span className="pagination-info">
                  Showing {Math.min(filteredRows.length, (rowsPage - 1) * rowsPerPage + 1)} to {Math.min(filteredRows.length, rowsPage * rowsPerPage)} of {filteredRows.length} items
                </span>
                <div className="pagination-btns">
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setRowsPage(p => Math.max(1, p - 1))}
                    disabled={rowsPage === 1}
                  >
                    Previous
                  </button>
                  <span style={{ display: 'inline-flex', alignItems: 'center', padding: '0 12px', fontSize: 13 }}>
                    Page {rowsPage} of {totalPages}
                  </span>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setRowsPage(p => Math.min(totalPages, p + 1))}
                    disabled={rowsPage === totalPages}
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

