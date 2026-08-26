import React, { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Search, ChevronLeft, ChevronRight, X, ChevronDown, ChevronUp, ExternalLink, Layers, FileText, CornerDownRight, Download, Trash2, CheckSquare } from 'lucide-react'
import quotationApi from '../api/quotationClient.js'
import GhostSearchInput from '../components/GhostSearchInput.jsx'
import { exportTableToExcel } from '../utils/excelExporter.js'

export function formatIndianCurrency(val) {
  if (val === null || val === undefined || val === '') return '₹0.00'
  const num = parseFloat(String(val).replace(/,/g, ''))
  if (isNaN(num)) return String(val)
  
  const fixed = num.toFixed(2)
  const parts = fixed.split('.')
  let integerPart = parts[0]
  const decimalPart = parts[1]

  const isNegative = integerPart.startsWith('-')
  if (isNegative) {
    integerPart = integerPart.substring(1)
  }

  let lastThree = integerPart.substring(integerPart.length - 3)
  const otherNumbers = integerPart.substring(0, integerPart.length - 3)
  if (otherNumbers !== '') {
    lastThree = ',' + lastThree
  }
  const formattedInteger = otherNumbers.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + lastThree
  
  return `${isNegative ? '-' : ''}₹${formattedInteger}.${decimalPart}`
}

export function formatDocumentType(type) {
  if (!type) return 'Document'
  const lower = String(type).toLowerCase()
  switch (lower) {
    case 'purchase_order': return 'Purchase Order'
    case 'quotation': return 'Quotation'
    case 'invoice_proforma': return 'Proforma Invoice'
    case 'invoice_final': return 'Tax Invoice'
    case 'patient_account_statement': return 'Patient Statement'
    default: return String(type).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }
}

export function getDocTypeColor(type) {
  if (!type) return 'var(--text-secondary)'
  const lower = String(type).toLowerCase()
  switch (lower) {
    case 'purchase_order': return '#38bdf8'     // Electric Azure Cyan
    case 'quotation': return '#818cf8'          // Indigo Violet
    case 'invoice_proforma': return '#fbbf24'   // Sun Gold Amber
    case 'invoice_final': return '#2dd4bf'      // Vibrant Mint Emerald
    case 'patient_account_statement': return '#c084fc' // Orchid Purple
    default: return '#38bdf8'
  }
}

export function getFileFormat(filename) {
  if (!filename) return 'PDF'
  const ext = filename.split('.').pop().toLowerCase()
  if (ext === 'csv') return 'CSV'
  if (['xlsx', 'xls'].includes(ext)) return 'EXCEL'
  if (['jpg', 'jpeg', 'png', 'webp'].includes(ext)) return 'JPG'
  return 'PDF'
}

export function getFileFormatBadgeStyle(format) {
  switch (format) {
    case 'CSV':
      return { background: 'rgba(34, 197, 94, 0.15)', color: 'var(--green)', border: '1px solid rgba(34, 197, 94, 0.3)' }
    case 'EXCEL':
      return { background: 'rgba(16, 185, 129, 0.15)', color: '#10b981', border: '1px solid rgba(16, 185, 129, 0.3)' }
    case 'JPG':
      return { background: 'rgba(168, 85, 247, 0.15)', color: 'var(--purple)', border: '1px solid rgba(168, 85, 247, 0.3)' }
    default: // PDF
      return { background: 'rgba(239, 68, 68, 0.15)', color: 'var(--red)', border: '1px solid rgba(239, 68, 68, 0.3)' }
  }
}

function HighlightMatch({ text, query }) {
  if (!text || text === null || text === undefined) return <span></span>
  const displayStr = String(text).replace(/[\r\n]+/g, ' ')
  if (!query || !query.trim()) return <span>{displayStr}</span>

  const cleanQ = query.trim()
  const tokens = cleanQ.split(/\s+/).filter(Boolean)
  if (tokens.length === 0) return <span>{displayStr}</span>

  const escTokens = tokens.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const regex = new RegExp(`(${escTokens.join('|')})`, 'gi')

  const parts = displayStr.split(regex)
  return (
    <span>
      {parts.map((part, i) =>
        tokens.some(t => t.toLowerCase() === part.toLowerCase()) ? (
          <mark key={i} style={{ background: 'rgba(0, 212, 255, 0.35)', color: '#fff', borderRadius: 2, padding: '0 2px' }}>
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </span>
  )
}

export default function QuotationsList() {
  const [searchParams] = useSearchParams()
  const initialStatus = searchParams.get('status') || ''
  const initialType = searchParams.get('type') || searchParams.get('doc_type') || ''

  const [quotations, setQuotations] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [limit] = useState(10)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState(initialStatus)
  const [docType, setDocType] = useState(initialType)
  const [loading, setLoading] = useState(false)
  const [expandedDocs, setExpandedDocs] = useState({})
  const [searchMode, setSearchMode] = useState('documents') // 'documents' | 'flat_items'
  const [flatLineItems, setFlatLineItems] = useState([])
  const [flatLoading, setFlatLoading] = useState(false)
  
  // Selection and Deletion State
  const [selectedDocIds, setSelectedDocIds] = useState([])

  const fetchQuotations = async ({ currentSearch = search, currentStatus = status, currentDocType = docType, currentPage = page } = {}) => {
    setLoading(true)
    try {
      if (currentSearch && currentSearch.trim()) {
        const res = await quotationApi.searchDocuments({
          q: currentSearch,
          document_type: currentDocType || undefined,
        })
        const items = res.items || []
        setQuotations(items)
        setTotal(items.length)

        const expandState = {}
        items.forEach(q => {
          if (q.matching_line_items && q.matching_line_items.length > 0) {
            expandState[q.id] = true
          }
        })
        setExpandedDocs(expandState)
      } else {
        const res = await quotationApi.listQuotations({
          page: currentPage,
          limit,
          status: currentStatus,
          document_type: currentDocType,
        })
        setQuotations(res.items || [])
        setTotal(res.total || 0)
      }
    } catch (err) {
      console.error('Failed to fetch quotations:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchFlatLineItems = async (q) => {
    if (!q || !q.trim()) {
      setFlatLineItems([])
      return
    }
    setFlatLoading(true)
    try {
      const res = await quotationApi.searchLineItems(q)
      setFlatLineItems(res.items || [])
    } catch (err) {
      console.error('Failed to fetch line items:', err)
    } finally {
      setFlatLoading(false)
    }
  }

  useEffect(() => {
    fetchQuotations()
  }, [page, status, docType])

  useEffect(() => {
    if (searchMode === 'flat_items' && search.trim()) {
      fetchFlatLineItems(search)
    }
  }, [search, searchMode])

  const totalPages = Math.ceil(total / limit)

  const toggleDocExpand = (docId) => {
    setExpandedDocs(prev => ({
      ...prev,
      [docId]: !prev[docId]
    }))
  }

  const toggleSelectAll = () => {
    if (selectedDocIds.length === quotations.length && quotations.length > 0) {
      setSelectedDocIds([])
    } else {
      setSelectedDocIds(quotations.map(q => q.id))
    }
  }

  const toggleSelectDoc = (id) => {
    setSelectedDocIds(prev =>
      prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]
    )
  }

  const handleDeleteSingle = async (id, docNo) => {
    if (!window.confirm(`Are you sure you want to delete Document #${docNo || id}? This will permanently delete the document and all associated line items.`)) {
      return
    }
    try {
      await quotationApi.deleteQuotation(id)
      setSelectedDocIds(prev => prev.filter(item => item !== id))
      fetchQuotations()
    } catch (err) {
      alert(`Failed to delete document: ${err.message}`)
    }
  }

  const handleBatchDelete = async () => {
    if (selectedDocIds.length === 0) return
    if (!window.confirm(`Are you sure you want to delete ${selectedDocIds.length} selected document(s)? This will permanently delete them and all associated line items.`)) {
      return
    }
    try {
      await quotationApi.batchDeleteQuotations(selectedDocIds)
      setSelectedDocIds([])
      fetchQuotations()
    } catch (err) {
      alert(`Failed to batch delete documents: ${err.message}`)
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>Documents & Items Explorer</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
            Universal multi-column search across all document headers, item rows, descriptions, CPT codes, and monetary values
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: 4, borderRadius: 8, border: '1px solid var(--border)', display: 'flex', gap: 4 }}>
            <button
              className={`btn btn-sm ${searchMode === 'documents' ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setSearchMode('documents')}
              style={{ fontSize: 12 }}
            >
              Document View
            </button>
            <button
              className={`btn btn-sm ${searchMode === 'flat_items' ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => {
                setSearchMode('flat_items')
                if (search.trim()) fetchFlatLineItems(search)
              }}
              style={{ fontSize: 12 }}
            >
              Line Items View
            </button>
          </div>
          <Link to="/upload" className="btn btn-primary">
            Ingest New Document
          </Link>
        </div>
      </div>

      {/* Filters Toolbar Card */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="flex justify-between items-center gap-3" style={{ flexWrap: 'wrap' }}>
          <div style={{ flex: '1', minWidth: 320 }}>
            <GhostSearchInput
              value={search}
              onChange={(val) => {
                setSearch(val)
                setPage(1)
              }}
              onSubmit={() => setPage(1)}
              placeholder="Search any item, CPT code, vendor, customer, rate, or amount..."
            />
          </div>

          <div className="flex items-center gap-2">
            <select
              className="select"
              value={docType}
              onChange={(e) => {
                setDocType(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Document Types</option>
              <option value="purchase_order">Purchase Order</option>
              <option value="quotation">Quotation</option>
              <option value="invoice_proforma">Proforma Invoice</option>
              <option value="invoice_final">Tax Invoice</option>
              <option value="patient_account_statement">Patient Account Statement</option>
            </select>

            <select
              className="select"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All Statuses</option>
              <option value="ok">Ok</option>
              <option value="needs_review">Needs Review</option>
            </select>

            {(search || status || docType) && (
              <button
                className="btn btn-secondary btn-icon"
                onClick={() => {
                  setSearch('')
                  setStatus('')
                  setDocType('')
                  setPage(1)
                  fetchQuotations({ currentSearch: '', currentStatus: '', currentDocType: '', currentPage: 1 })
                }}
                title="Clear all filters"
              >
                <X size={16} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* MODE A: Documents View */}
      {searchMode === 'documents' && (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-container" style={{ border: 'none', borderRadius: 0, marginBottom: 0 }}>
            <table className="quote-table">
              <thead>
                <tr>
                  <th style={{ width: 32 }}></th>
                  <th>Doc Type</th>
                  <th>Format</th>
                  <th>Doc / Ref #</th>
                  <th>Vendor / Hospital</th>
                  <th>Customer / Patient</th>
                  <th>Doc Date</th>
                  <th className="text-right">Grand Total</th>
                  <th>Audit Status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan="10" style={{ textAlign: 'center', padding: '40px 0' }}>
                      <div style={{ display: 'inline-block' }} className="spinner"></div>
                      <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-secondary)' }}>Searching documents & items...</div>
                    </td>
                  </tr>
                ) : quotations.length === 0 ? (
                  <tr>
                    <td colSpan="10" style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-secondary)' }}>
                      No documents found matching the search criteria.
                    </td>
                  </tr>
                ) : (
                  quotations.map((q) => {
                    const format = getFileFormat(q.source_file)
                    const isExpanded = expandedDocs[q.id]
                    const matchItems = q.matching_line_items || []

                    return (
                      <React.Fragment key={q.id}>
                        <tr
                          style={{
                            background: isExpanded ? 'rgba(0, 212, 255, 0.02)' : undefined,
                            cursor: 'pointer',
                            transition: 'background 0.15s ease'
                          }}
                          onClick={(e) => {
                            if (e.target.closest('button') || e.target.closest('input') || e.target.closest('a')) return
                            navigate(`/quotations/${q.id}`)
                          }}
                        >
                          <td>
                            {matchItems.length > 0 && (
                              <button
                                type="button"
                                className="btn-icon"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  toggleDocExpand(q.id)
                                }}
                                style={{ width: 24, height: 24, color: 'var(--cyan)' }}
                                title="Toggle matching line items"
                              >
                                {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                              </button>
                            )}
                          </td>
                          <td>
                            <span style={{ 
                              color: getDocTypeColor(q.document_type), 
                              fontWeight: 700, 
                              fontSize: 11, 
                              textTransform: 'uppercase',
                              background: `${getDocTypeColor(q.document_type)}1A`,
                              padding: '3px 8px',
                              borderRadius: 4
                            }}>
                              {formatDocumentType(q.document_type)}
                            </span>
                          </td>
                          <td>
                            <span style={{
                              fontSize: 11,
                              fontWeight: 700,
                              padding: '3px 8px',
                              borderRadius: 4,
                              letterSpacing: '0.04em',
                              ...getFileFormatBadgeStyle(format)
                            }}>
                              {format}
                            </span>
                          </td>
                          <td style={{ fontWeight: 600, color: '#fff' }}>
                            <HighlightMatch text={q.quotation_no || `ID: ${q.id}`} query={search} />
                          </td>
                          <td><HighlightMatch text={q.vendor_name} query={search} /></td>
                          <td><HighlightMatch text={q.customer_name} query={search} /></td>
                          <td>
                            {q.quotation_date ? new Date(q.quotation_date).toLocaleDateString('en-IN', {
                              day: '2-digit',
                              month: 'short',
                              year: 'numeric'
                            }) : 'N/A'}
                          </td>
                          <td className="text-right" style={{ fontWeight: 600, color: 'var(--cyan)' }}>
                            {formatIndianCurrency(q.grand_total_final)}
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span className={`badge badge-${q.extraction_status || 'ok'}`}>
                                <span className="badge-dot" />
                                {q.extraction_status === 'needs_review' ? 'Needs Review' : 'Ok'}
                              </span>
                              {matchItems.length > 0 && (
                                <span style={{ fontSize: 10, fontWeight: 700, background: 'rgba(0, 212, 255, 0.15)', color: 'var(--cyan)', padding: '2px 6px', borderRadius: 4, border: '1px solid rgba(0, 212, 255, 0.3)' }}>
                                  {matchItems.length} Match{matchItems.length > 1 ? 'es' : ''}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="text-right" onClick={(e) => e.stopPropagation()}>
                            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', alignItems: 'center' }}>
                              <Link to={`/quotations/${q.id}`} className="btn btn-secondary btn-sm" style={{ padding: '4px 10px' }}>
                                View
                              </Link>
                              <button
                                type="button"
                                className="btn-icon"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  handleDeleteSingle(q.id, q.quotation_no)
                                }}
                                style={{ color: 'var(--red)', width: 28, height: 28, borderColor: 'rgba(244, 63, 94, 0.2)', background: 'rgba(244, 63, 94, 0.05)' }}
                                title="Delete document and its line items"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </td>
                        </tr>

                        {/* Expandable Drawer showing exact matching line items */}
                        {isExpanded && matchItems.length > 0 && (
                          <tr style={{ background: 'rgba(0, 212, 255, 0.03)' }}>
                            <td colSpan="11" style={{ padding: '12px 20px 16px 44px' }}>
                              <div style={{ borderLeft: '2px solid var(--cyan)', paddingLeft: 14 }}>
                                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cyan)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                                  <CornerDownRight size={14} /> Matching Line Items in Document #{q.id} ({matchItems.length})
                                </div>
                                <div className="table-container" style={{ marginBottom: 0, border: '1px solid var(--border)', borderRadius: 6 }}>
                                  <table className="quote-table" style={{ fontSize: 12 }}>
                                    <thead>
                                      <tr>
                                        <th style={{ width: 40 }}>#</th>
                                        <th>Code / CPT</th>
                                        <th>Description / Procedure</th>
                                        <th className="text-right">Qty</th>
                                        <th className="text-right">Rate / Unit</th>
                                        <th className="text-right">Total Charges</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {matchItems.map((item, idx) => (
                                        <tr
                                          key={item.id || idx}
                                          style={{ cursor: 'pointer' }}
                                          onClick={() => navigate(`/quotations/${q.id}`)}
                                        >
                                          <td>{item.line_no}</td>
                                          <td style={{ fontWeight: 600, color: '#fff' }}>
                                            <HighlightMatch text={item.item_code} query={search} />
                                          </td>
                                          <td>
                                            <HighlightMatch text={item.description} query={search} />
                                          </td>
                                          <td className="text-right">{item.qty != null ? item.qty : '-'}</td>
                                          <td className="text-right">{item.rate != null ? formatIndianCurrency(item.rate) : '-'}</td>
                                          <td className="text-right" style={{ fontWeight: 700, color: 'var(--cyan)' }}>
                                            <HighlightMatch text={formatIndianCurrency(item.final_value || item.gross_amount)} query={search} />
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          {!search && totalPages > 1 && (
            <div className="flex justify-between items-center p-3" style={{ borderTop: '1px solid var(--border)', background: 'rgba(255,255,255,0.01)' }}>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                Showing {(page - 1) * limit + 1} to {Math.min(page * limit, total)} of {total} documents
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="btn btn-secondary btn-icon"
                  disabled={page === 1}
                  onClick={() => setPage(p => Math.max(p - 1, 1))}
                >
                  <ChevronLeft size={16} />
                </button>
                <span style={{ fontSize: 13, fontWeight: 600, padding: '0 8px' }}>
                  Page {page} of {totalPages}
                </span>
                <button
                  className="btn btn-secondary btn-icon"
                  disabled={page === totalPages}
                  onClick={() => setPage(p => Math.min(p + 1, totalPages))}
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* MODE B: Universal Flat Line Items View */}
      {searchMode === 'flat_items' && (
        <div className="card" style={{ padding: 0 }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,0.02)', fontSize: 12, color: 'var(--text-secondary)' }}>
            Showing <strong>{flatLineItems.length}</strong> matching item row(s) across all documents in database
          </div>
          <div className="table-container" style={{ border: 'none', borderRadius: 0, marginBottom: 0 }}>
            <table className="quote-table">
              <thead>
                <tr>
                  <th>Doc #</th>
                  <th>Doc Type</th>
                  <th>Vendor / Hospital</th>
                  <th>Customer / Patient</th>
                  <th>Code / CPT</th>
                  <th>Description / Procedure</th>
                  <th className="text-right">Qty</th>
                  <th className="text-right">Rate</th>
                  <th className="text-right">Total Charges</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {flatLoading ? (
                  <tr>
                    <td colSpan="10" style={{ textAlign: 'center', padding: '40px 0' }}>
                      <div style={{ display: 'inline-block' }} className="spinner"></div>
                      <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-secondary)' }}>Searching line items...</div>
                    </td>
                  </tr>
                ) : flatLineItems.length === 0 ? (
                  <tr>
                    <td colSpan="10" style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-secondary)' }}>
                      {search ? `No line items found matching query "${search}"` : 'Type a query in search bar above to find matching item rows across all documents'}
                    </td>
                  </tr>
                ) : (
                  flatLineItems.map((item) => (
                    <tr key={item.id}>
                      <td style={{ fontWeight: 600, color: '#fff' }}>
                        <Link to={`/quotations/${item.document_id}`} style={{ color: 'var(--cyan)', textDecoration: 'none' }}>
                          {item.quotation_no || `#${item.document_id}`}
                        </Link>
                      </td>
                      <td>
                        <span style={{ 
                          color: getDocTypeColor(item.document_type), 
                          fontWeight: 700, 
                          fontSize: 10, 
                          textTransform: 'uppercase',
                          background: `${getDocTypeColor(item.document_type)}1A`,
                          padding: '2px 6px',
                          borderRadius: 4
                        }}>
                          {formatDocumentType(item.document_type)}
                        </span>
                      </td>
                      <td><HighlightMatch text={item.vendor_name} query={search} /></td>
                      <td><HighlightMatch text={item.customer_name} query={search} /></td>
                      <td style={{ fontWeight: 600, color: '#fff' }}>
                        <HighlightMatch text={item.item_code} query={search} />
                      </td>
                      <td>
                        <HighlightMatch text={item.description} query={search} />
                      </td>
                      <td className="text-right">{item.qty != null ? item.qty : '-'}</td>
                      <td className="text-right">{item.rate != null ? formatIndianCurrency(item.rate) : '-'}</td>
                      <td className="text-right" style={{ fontWeight: 700, color: 'var(--cyan)' }}>
                        <HighlightMatch text={formatIndianCurrency(item.final_value || item.gross_amount)} query={search} />
                      </td>
                      <td className="text-right">
                        <Link to={`/quotations/${item.document_id}`} className="btn btn-secondary btn-sm" style={{ padding: '2px 8px', fontSize: 11 }}>
                          View Audit
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
