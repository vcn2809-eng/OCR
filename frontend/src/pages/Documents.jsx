import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { FileText, Search, RefreshCw, Eye, Trash2, Filter, Download } from 'lucide-react'
import api from '../api/client.js'
import { useToast } from '../ToastContext.jsx'
import DataTable from '../components/DataTable.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { exportTableToExcel } from '../utils/excelExporter.js'

export default function DocumentsPage() {
  const [documents, setDocuments] = useState([])
  const [vendors, setVendors] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filter States
  const [docTypeFilter, setDocTypeFilter] = useState('all')
  const [vendorFilter, setVendorFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [filenameSearch, setFilenameSearch] = useState('')

  const toast = useToast()

  // Fetch Vendor options for filter dropdown
  useEffect(() => {
    api.listVendors().then(v => setVendors(v || [])).catch(() => {})
  }, [])

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.listDocuments({
        page,
        page_size: 20,
        document_type: docTypeFilter !== 'all' ? docTypeFilter : undefined,
        vendor_id: vendorFilter !== 'all' ? vendorFilter : undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        filename: filenameSearch.trim() || undefined,
      })
      setDocuments(res.items || [])
      setTotal(res.total || 0)
    } catch (e) {
      setError(e.message)
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [page, docTypeFilter, vendorFilter, statusFilter, filenameSearch, toast])

  useEffect(() => { loadDocuments() }, [loadDocuments])

  const handleDelete = async (id, name, e) => {
    e.stopPropagation()
    if (!window.confirm(`Delete document "${name}"?`)) return
    try {
      await api.deleteDocument(id)
      toast(`Deleted document "${name}"`, 'success')
      loadDocuments()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const columns = [
    {
      header: 'Filename',
      accessor: 'original_filename',
      cell: (row) => (
        <Link to={`/documents/${row.document_id}`} style={{ color: 'var(--cyan)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
          <FileText size={15} /> {row.original_filename}
        </Link>
      ),
    },
    {
      header: 'Type',
      accessor: 'file_type',
      cell: (row) => <span style={{ textTransform: 'uppercase', fontSize: 11, fontFamily: 'monospace' }}>{row.file_type}</span>,
    },
    {
      header: 'Document Classification',
      accessor: 'document_type',
      cell: (row) => <span style={{ textTransform: 'capitalize' }}>{row.document_type || '—'}</span>,
    },
    {
      header: 'Status',
      accessor: 'status',
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      header: 'Uploaded At',
      accessor: 'uploaded_at',
      cell: (row) => <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{row.uploaded_at ? new Date(row.uploaded_at).toLocaleString() : '—'}</span>,
    },
    {
      header: 'Actions',
      align: 'right',
      cell: (row) => (
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
          <Link to={`/documents/${row.document_id}`} className="btn-icon" title="View details">
            <Eye size={13} />
          </Link>
          <button className="btn-icon" onClick={(e) => handleDelete(row.document_id, row.original_filename, e)} title="Delete">
            <Trash2 size={13} style={{ color: 'var(--red)' }} />
          </button>
        </div>
      ),
    },
  ]

  const handleExportExcel = () => {
    const cols = [
      { header: 'Document ID', key: 'document_id' },
      { header: 'Original Filename', key: 'original_filename' },
      { header: 'File Format', key: 'file_type' },
      { header: 'Classification', key: 'document_type' },
      { header: 'Status', key: 'status' },
      { header: 'Uploaded At', key: 'uploaded_at' },
    ]
    exportTableToExcel({ filename: 'eav_documents_list', columns: cols, data: documents })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>Document Explorer</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
            Filter and query all {total} stored documents in EAV schema
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={loadDocuments}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Filter Bar */}
      <div className="card mb-3" style={{ padding: '14px 18px' }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--cyan)', fontSize: 12, fontWeight: 600 }}>
            <Filter size={14} /> Filters:
          </div>

          {/* Document Type Dropdown */}
          <select className="select" value={docTypeFilter} onChange={e => { setDocTypeFilter(e.target.value); setPage(1) }}>
            <option value="all">All Types</option>
            <option value="invoice">Invoice</option>
            <option value="resume">Resume</option>
            <option value="financial_statement">Financial Statement</option>
            <option value="generic">Generic</option>
          </select>

          {/* Vendor Dropdown */}
          <select className="select" value={vendorFilter} onChange={e => { setVendorFilter(e.target.value); setPage(1) }}>
            <option value="all">All Vendors</option>
            {vendors.map(v => (
              <option key={v.vendor_id} value={v.vendor_id}>{v.vendor_name}</option>
            ))}
          </select>

          {/* Status Dropdown */}
          <select className="select" value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }}>
            <option value="all">All Statuses</option>
            <option value="stored">Stored</option>
            <option value="processing">Processing</option>
            <option value="quarantined">Quarantined</option>
            <option value="failed">Failed</option>
          </select>

          {/* Search Box */}
          <div className="search-wrap" style={{ flex: 1, minWidth: 200 }}>
            <Search size={14} />
            <input
              className="input"
              placeholder="Search filename..."
              value={filenameSearch}
              onChange={e => { setFilenameSearch(e.target.value); setPage(1) }}
            />
          </div>
        </div>
      </div>

      {/* Explicit Error State */}
      {error && (
        <div style={{ background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', borderRadius: 8, padding: 14, color: '#f43f5e', fontSize: 13, marginBottom: 16 }}>
          ⚠ Error loading documents: {error}
        </div>
      )}

      {/* Data Table Component */}
      <DataTable
        columns={columns}
        data={documents}
        loading={loading}
        emptyMessage="No documents found matching filters."
      />
    </div>
  )
}
