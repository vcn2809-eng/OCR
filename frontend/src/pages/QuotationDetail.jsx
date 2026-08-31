import React, { useState, useEffect } from 'react'
import { useParams, useLocation, Link } from 'react-router-dom'
import { ArrowLeft, AlertTriangle, CheckCircle, Info, Edit3, Save, Search, X, Download, Columns, ZoomIn, ZoomOut, RotateCw, ExternalLink, FileText, Maximize2, LayoutGrid, ListFilter, DollarSign, Calculator } from 'lucide-react'
import quotationApi from '../api/quotationClient.js'
import { formatIndianCurrency, formatDocumentType, getDocTypeColor, getFileFormat } from './QuotationsList.jsx'
import { useToast } from '../ToastContext.jsx'
import GhostSearchInput from '../components/GhostSearchInput.jsx'
import { exportTableToExcel } from '../utils/excelExporter.js'

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

export default function QuotationDetail() {
  const { id } = useParams()
  const location = useLocation()
  const toast = useToast()
  const [quotation, setQuotation] = useState(null)
  const [lineItems, setLineItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [docSearch, setDocSearch] = useState('')
  
  // View Mode: 'template' (Matches Document Template) | 'all_cols' (Standard 18 Accounting Columns)
  const [viewMode, setViewMode] = useState('template')

  // Split View and Document Viewer States
  const [isSplitView, setIsSplitView] = useState(false)
  const [zoomLevel, setZoomLevel] = useState(1.0)
  const [rotation, setRotation] = useState(0)

  // Track which cell is being edited: { itemId, fieldName }
  const [editingCell, setEditingCell] = useState(null)
  const [editValue, setEditValue] = useState('')

  const loadQuotationData = async () => {
    try {
      const res = await quotationApi.getQuotation(id)
      setQuotation(res)
      setLineItems(res.line_items || [])
    } catch (err) {
      console.error(err)
      toast(`Failed to load quotation detail: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadQuotationData()
  }, [id])

  const handleCellClick = (item, field) => {
    setEditingCell({ itemId: item.id, fieldName: field })
    setEditValue(String(item[field] || ''))
  }

  const handleCellSave = async (item, field) => {
    if (!editingCell) return

    if (String(item[field]) === editValue) {
      setEditingCell(null)
      return
    }

    try {
      const updateFields = { [field]: editValue }
      const res = await quotationApi.updateLineItem(item.id, updateFields)
      
      setLineItems(prev => prev.map(row => {
        if (row.id === item.id) {
          return res.line_item
        }
        return row
      }))

      setQuotation(prev => ({
        ...prev,
        extraction_status: res.quotation_status
      }))

      toast('Line item updated & re-validated successfully!', 'success')
    } catch (err) {
      toast(`Failed to save edit: ${err.message}`, 'error')
    } finally {
      setEditingCell(null)
    }
  }

  const handleKeyDown = (e, item, field) => {
    if (e.key === 'Enter') {
      handleCellSave(item, field)
    } else if (e.key === 'Escape') {
      setEditingCell(null)
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <div className="spinner" style={{ display: 'inline-block' }}></div>
        <div style={{ marginTop: 16, color: 'var(--text-secondary)' }}>Loading quotation details...</div>
      </div>
    )
  }

  if (!quotation) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '40px' }}>
        <AlertTriangle size={32} style={{ color: 'var(--red)', marginBottom: 12 }} />
        <h3>Quotation not found</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>The requested quotation does not exist or has been deleted.</p>
        <Link to="/quotations" className="btn btn-secondary mt-3">Back to Directory</Link>
      </div>
    )
  }

  // Filter line items based on in-document search query
  const filteredLineItems = lineItems.filter(item => {
    if (!docSearch || !docSearch.trim()) return true
    const cleanQ = docSearch.toLowerCase().trim()
    const tokens = cleanQ.split(/\s+/).filter(Boolean)
    
    return Object.entries(item).some(([key, val]) => {
      if (val === null || val === undefined) return false
      const normalizedVal = String(val).toLowerCase().replace(/[\s\r\n]+/g, ' ')
      if (normalizedVal.includes(cleanQ)) return true
      return tokens.every(tok => normalizedVal.includes(tok))
    })
  })

  // Dynamically derive columns that match this document's visual template
  const docType = quotation.document_type || 'generic'
  const isMedical = docType.includes('medical') || docType.includes('statement') || (quotation.source_file && quotation.source_file.includes('hospital')) || (quotation.source_file && quotation.source_file.includes('med_doc'))
  const isPO = docType.includes('purchase') || docType.includes('po')

  // Calculate live client-side sums & adjustments reconciliation
  const sumOfTaxable = lineItems.reduce((acc, item) => {
    const val = parseFloat(String(item.taxable_amount || item.gross_amount || '0').replace(/,/g, '')) || 0
    return acc + val
  }, 0)

  const sumOfLineDiscounts = lineItems.reduce((acc, item) => {
    const val = parseFloat(String(item.discount_amount || '0').replace(/,/g, '')) || 0
    return acc + val
  }, 0)

  const sumOfFinal = lineItems.reduce((acc, item) => {
    const val = parseFloat(String(item.final_value || item.gross_amount || '0').replace(/,/g, '')) || 0
    return acc + val
  }, 0)

  const expectedTaxable = parseFloat(String(quotation.grand_total_taxable || '0').replace(/,/g, '')) || 0
  const expectedFinal = parseFloat(String(quotation.grand_total_final || '0').replace(/,/g, '')) || 0

  // Billed charges and net due calculation with OCR artifact protection
  const billedCharges = expectedTaxable > 0 ? expectedTaxable : sumOfFinal
  
  // If expectedFinal is a small OCR artifact (e.g. 27.21 instead of 27205.88), prefer sumOfFinal
  const isNetDueValid = expectedFinal > 0 && (Math.abs(expectedFinal - sumOfFinal) < 500.0 || (billedCharges > expectedFinal && expectedFinal > (billedCharges * 0.1)))
  const netDue = isNetDueValid ? expectedFinal : sumOfFinal
  
  // Total Discounts / Write-offs
  const rawDiffDiscount = (billedCharges > netDue) ? (billedCharges - netDue) : 0;
  const totalDiscounts = sumOfLineDiscounts > 0 ? sumOfLineDiscounts : rawDiffDiscount;

  // Mathematical Reconciliation Check (Requirement 3):
  // Check if computed line-item sum matches printed subtotal (if present) and grand total within tolerance.
  const isSubtotalReconciled = expectedTaxable > 0 ? Math.abs(sumOfFinal - expectedTaxable) <= 2.0 : true;
  const isFinalReconciled = expectedFinal > 0 ? (
    Math.abs(sumOfFinal - expectedFinal) <= 2.0 || 
    Math.abs((sumOfFinal - sumOfLineDiscounts) - expectedFinal) <= 2.0 ||
    Math.abs((sumOfFinal - rawDiffDiscount) - expectedFinal) <= 2.0
  ) : true;
  const isFullyReconciled = isSubtotalReconciled && isFinalReconciled;

  const justUploaded = location.state?.justUploaded
  const uploadStatus = location.state?.status

  const allColumnsList = [
    { key: 'line_no', header: '#', alwaysShow: true, width: '40px' },
    { key: 'item_date', header: 'Date', alwaysShow: isMedical, minWidth: '95px' },
    { key: 'item_code', header: isMedical ? 'CPT / Code' : (isPO ? 'Part #' : 'Item Code') },
    { key: 'description', header: isMedical ? 'Procedure / Service' : 'Description', alwaysShow: true, minWidth: '220px' },
    { key: 'hsn_code', header: 'HSN / SAC' },
    { key: 'brand', header: isMedical ? 'Dept / Facility' : 'Brand' },
    { key: 'uom', header: 'UOM' },
    { key: 'packing', header: 'Packing / Size' },
    { key: 'qty', header: isPO ? 'Ordered Qty' : 'Qty', align: 'right' },
    { key: 'rate', header: isMedical ? 'Unit Rate' : 'Rate', align: 'right' },
    { key: 'gross_amount', header: isMedical ? 'Billed Charges' : 'Gross Amt', align: 'right' },
    { key: 'discount_pct', header: 'Disc %', align: 'right' },
    { key: 'discount_amount', header: isMedical ? 'Insurance Adjustments' : 'Disc Amt', align: 'right' },
    { key: 'taxable_amount', header: 'Taxable Amt', align: 'right' },
    { key: 'cgst_pct', header: 'CGST %', align: 'right' },
    { key: 'cgst_amount', header: 'CGST Amt', align: 'right' },
    { key: 'sgst_pct', header: 'SGST %', align: 'right' },
    { key: 'sgst_amount', header: 'SGST Amt', align: 'right' },
    { key: 'final_value', header: isMedical ? 'Patient Due / Charges' : 'Final Value', align: 'right', alwaysShow: true },
    { key: 'status_eta', header: 'Status / ETA' }
  ]

  // Filter columns that actually contain data for THIS document
  const activeTemplateColumns = allColumnsList.filter(col => {
    if (viewMode === 'all_cols') return true
    if (col.alwaysShow) return true
    return lineItems.some(item => {
      const val = item[col.key]
      if (val === null || val === undefined || val === '') return false
      const str = String(val).trim()
      if (isMedical && (col.key === 'uom' || col.key === 'qty' || col.key === 'rate' || col.key === 'gross_amount')) {
        if (str === 'Nos' || str === '1' || str === '1.00') return false
      }
      return str !== '0' && str !== '0.00' && str !== 'N/A' && str !== '-'
    })
  })

  const handleExportExcel = () => {
    const cols = activeTemplateColumns.map(c => ({ header: c.header, key: c.key }))
    const filename = `document_${quotation.quotation_no || quotation.id}_items`
    exportTableToExcel({ filename, columns: cols, data: filteredLineItems })
  }

  const fileFormat = getFileFormat(quotation.source_file)
  const sourceFileUrl = `/files/${quotation.source_file}`


  return (
    <div>
      {/* Navigation and Title */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/quotations" className="btn-icon">
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>
                {quotation.quotation_no || `Document #${quotation.id}`}
              </h1>
              <span style={{ 
                color: getDocTypeColor(quotation.document_type), 
                fontWeight: 700, 
                fontSize: 11, 
                textTransform: 'uppercase',
                background: `${getDocTypeColor(quotation.document_type)}1A`,
                padding: '3px 8px',
                borderRadius: 4
              }}>
                {formatDocumentType(quotation.document_type)}
              </span>
              <span className={`badge badge-${isFullyReconciled ? 'ok' : 'needs_review'}`}>
                <span className="badge-dot" />
                {isFullyReconciled ? 'Reconciled' : 'Needs Audit Review'}
              </span>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
              Source File: <strong style={{ color: '#fff' }}>{quotation.source_file}</strong>
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          {/* Split-Screen Compare Button */}
          <button
            type="button"
            className={`btn ${isSplitView ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setIsSplitView(!isSplitView)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, borderColor: isSplitView ? 'var(--cyan)' : undefined }}
          >
            <Columns size={16} />
            {isSplitView ? 'Exit Split Screen' : 'Compare Original Document'}
          </button>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleExportExcel}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--green)', borderColor: 'rgba(34, 197, 94, 0.3)', background: 'rgba(34, 197, 94, 0.1)' }}
          >
            <Download size={16} /> Download Excel (.xlsx)
          </button>

          <Link to="/quotations" className="btn btn-secondary">
            Back to Explorer
          </Link>
        </div>
      </div>

      {justUploaded && (
        <div style={{ background: 'rgba(34, 197, 94, 0.08)', border: '1px solid rgba(34, 197, 94, 0.2)', borderRadius: 10, padding: 16, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
          <CheckCircle size={20} style={{ color: 'var(--green)' }} />
          <div>
            <strong style={{ display: 'block', color: '#fff', fontSize: 14 }}>Document Ingested Successfully!</strong>
            <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
              Status: <strong>{uploadStatus === 'needs_review' ? 'Needs Audit Review' : 'Valid & Verified'}</strong>. You can review and edit line item values below.
            </span>
          </div>
        </div>
      )}

      {/* Document Overview Header Meta Grid */}
      <div className="card mb-4" style={{ padding: 20 }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 16px 0', borderBottom: '1px solid var(--border)', paddingBottom: 10 }}>
          Header Metadata
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 20 }}>
          <div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Vendor</span>
            <strong style={{ fontSize: 14, color: '#fff' }}>{quotation.vendor_name || 'N/A'}</strong>
            {quotation.vendor_gstin && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>GSTIN: {quotation.vendor_gstin}</div>}
            {quotation.vendor_address && (
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4, whiteSpace: 'pre-line' }}>
                📍 {quotation.vendor_address}
              </div>
            )}
          </div>

          <div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Customer / Buyer / Patient</span>
            <strong style={{ fontSize: 14, color: '#fff' }}>{quotation.customer_name || 'N/A'}</strong>
            {quotation.customer_gstin && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>GSTIN: {quotation.customer_gstin}</div>}
            {quotation.customer_address && (
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4, whiteSpace: 'pre-line' }}>
                📍 {quotation.customer_address}
              </div>
            )}
          </div>

          <div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Document Date</span>
            <strong style={{ fontSize: 14, color: '#fff' }}>
              {quotation.quotation_date ? new Date(quotation.quotation_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : 'N/A'}
            </strong>
          </div>

          <div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Net Amount Due</span>
            <strong style={{ fontSize: 16, color: 'var(--green)' }}>
              {formatIndianCurrency(netDue)}
            </strong>
          </div>
        </div>
      </div>

      {/* Financial Summary & Adjustments Audit Card */}
      <div className="card mb-4" style={{ padding: 20, background: 'rgba(15, 23, 42, 0.85)', border: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, borderBottom: '1px solid var(--border)', paddingBottom: 10 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8, color: '#fff' }}>
            <Calculator size={16} style={{ color: 'var(--cyan)' }} /> Financial Summary & Adjustments Reconciliation
          </h3>
          <span className={`badge badge-${isFullyReconciled ? 'ok' : 'needs_review'}`}>
            <span className="badge-dot" />
            {isFullyReconciled ? 'Reconciled & Verified ✓' : 'Audit Mismatch Alert'}
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 20 }}>
          <div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>
              {isMedical ? 'Total Billed Charges' : 'Taxable Subtotal / Gross'}
            </span>
            <strong style={{ fontSize: 16, color: '#fff' }}>
              {formatIndianCurrency(billedCharges)}
            </strong>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
              Sum of {lineItems.length} Line Item(s): {formatIndianCurrency(sumOfFinal)}
            </div>
          </div>

          <div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>
              {isMedical ? 'Insurance Adjustments & Allowances' : 'Total Discounts / Write-offs'}
            </span>
            <strong style={{ fontSize: 16, color: totalDiscounts > 0 ? 'var(--cyan)' : 'var(--text-muted)' }}>
              {totalDiscounts > 0 ? `-${formatIndianCurrency(totalDiscounts)}` : '₹0.00'}
            </strong>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
              {totalDiscounts > 0 ? 'Discount / Deduction Recorded' : 'No Adjustments Recorded'}
            </div>
          </div>

          <div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>
              {isMedical ? 'Net Patient Amount Due' : 'Final Net Invoice Amount'}
            </span>
            <strong style={{ fontSize: 18, color: 'var(--green)' }}>
              {formatIndianCurrency(netDue)}
            </strong>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
              Calculated Net: {formatIndianCurrency(billedCharges - totalDiscounts)}
            </div>
          </div>
        </div>

        {isFullyReconciled ? (
          <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.05)', fontSize: 12, color: 'var(--green)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <CheckCircle size={14} />
            <span>
              <strong>Financial Verification Passed:</strong> Extracted line item sum ({formatIndianCurrency(sumOfFinal)}) reconciles with document net due ({formatIndianCurrency(netDue)}).
            </span>
          </div>
        ) : (
          <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid rgba(244, 63, 94, 0.2)', fontSize: 12, color: 'var(--red)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <AlertTriangle size={14} />
            <span>
              <strong>Grand Total Mismatch Alert:</strong> Extracted line item sum ({formatIndianCurrency(sumOfFinal)}) does not reconcile with document net due ({formatIndianCurrency(netDue)}). Delta: {formatIndianCurrency(Math.abs(sumOfFinal - netDue))}.
            </span>
          </div>
        )}
      </div>

      {/* MAIN CONTENT WORKSPACE: Full Width OR Split Screen 50/50 Dual Pane */}
      <div style={{ display: 'grid', gridTemplateColumns: isSplitView ? '1fr 1fr' : '1fr', gap: 20 }}>
        
        {/* LEFT PANE: Original Document Visual Viewer */}
        {isSplitView && (
          <div className="card" style={{ padding: 0, display: 'flex', flexDirection: 'column', height: 'calc(100vh - 220px)', position: 'sticky', top: 20, overflow: 'hidden' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,0.02)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileText size={16} style={{ color: 'var(--cyan)' }} />
                <strong style={{ fontSize: 13, color: '#fff' }}>Original Source Document ({fileFormat})</strong>
              </div>

              {/* Viewer Controls for Images */}
              {['JPG', 'PNG', 'JPEG'].includes(fileFormat) && (
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <button type="button" className="btn-icon" onClick={() => setZoomLevel(z => Math.min(z + 0.25, 3.0))} title="Zoom In">
                    <ZoomIn size={14} />
                  </button>
                  <button type="button" className="btn-icon" onClick={() => setZoomLevel(z => Math.max(z - 0.25, 0.5))} title="Zoom Out">
                    <ZoomOut size={14} />
                  </button>
                  <button type="button" className="btn-icon" onClick={() => setRotation(r => (r + 90) % 360)} title="Rotate Clockwise">
                    <RotateCw size={14} />
                  </button>
                  <button type="button" className="btn-icon" onClick={() => { setZoomLevel(1.0); setRotation(0) }} title="Reset Zoom">
                    <Maximize2 size={14} />
                  </button>
                </div>
              )}

              <a
                href={sourceFileUrl}
                target="_blank"
                rel="noreferrer"
                className="btn btn-ghost btn-sm"
                style={{ fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--cyan)' }}
              >
                Open File <ExternalLink size={12} />
              </a>
            </div>

            {/* Document Render Viewport */}
            <div style={{ flex: 1, background: '#0a0d14', overflow: 'auto', display: 'flex', justifyContent: 'center', alignItems: 'center', padding: 16 }}>
              {fileFormat === 'PDF' ? (
                <iframe
                  src={sourceFileUrl}
                  title="PDF Source Document"
                  style={{ width: '100%', height: '100%', border: 'none', borderRadius: 4 }}
                />
              ) : ['JPG', 'PNG', 'JPEG'].includes(fileFormat) ? (
                <div style={{ overflow: 'auto', textAlign: 'center', width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                  <img
                    src={sourceFileUrl}
                    alt="Original Document Source"
                    style={{
                      maxWidth: '100%',
                      transform: `scale(${zoomLevel}) rotate(${rotation}deg)`,
                      transition: 'transform 0.2s ease',
                      borderRadius: 4,
                      boxShadow: '0 8px 24px rgba(0,0,0,0.5)'
                    }}
                  />
                </div>
              ) : (
                <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-secondary)' }}>
                  <FileText size={32} style={{ color: 'var(--cyan)', marginBottom: 10 }} />
                  <div style={{ fontWeight: 600, color: '#fff', marginBottom: 4 }}>Spreadsheet / CSV Raw Data Source</div>
                  <div style={{ fontSize: 12, marginBottom: 12 }}>Source file: {quotation.source_file}</div>
                  <a href={sourceFileUrl} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
                    Download Source File ({fileFormat})
                  </a>
                </div>
              )}
            </div>
          </div>
        )}

        {/* RIGHT PANE: Extracted Line Items & Audit Table Container */}
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,0.01)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <h3 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>
                  Document Table ({filteredLineItems.length} of {lineItems.length} Rows)
                </h3>
                <span style={{ fontSize: 11, background: 'rgba(0, 212, 255, 0.1)', color: 'var(--cyan)', padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>
                  {viewMode === 'template' ? `Document Template (${activeTemplateColumns.length} Cols)` : 'All 18 Cols'}
                </span>
              </div>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'block', marginTop: 2 }}>
                Click on any cell to edit inline.
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {/* View Mode Toggle Switch */}
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: 3, borderRadius: 8, border: '1px solid var(--border)', display: 'flex', gap: 3 }}>
                <button
                  type="button"
                  className={`btn btn-sm ${viewMode === 'template' ? 'btn-primary' : 'btn-ghost'}`}
                  onClick={() => setViewMode('template')}
                  style={{ fontSize: 11, padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                  title="Show only column headers matching this original document template"
                >
                  <LayoutGrid size={13} /> Original Template
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${viewMode === 'all_cols' ? 'btn-primary' : 'btn-ghost'}`}
                  onClick={() => setViewMode('all_cols')}
                  style={{ fontSize: 11, padding: '4px 10px', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                  title="Show all 18 standardized accounting columns"
                >
                  <ListFilter size={13} /> All Accounting Cols
                </button>
              </div>

              {/* In-Document Search Input */}
              <div style={{ minWidth: 220, flex: '1', maxWidth: 300 }}>
                <GhostSearchInput
                  value={docSearch}
                  onChange={(val) => setDocSearch(val)}
                  placeholder="Search table values..."
                  style={{ margin: 0 }}
                />
              </div>
            </div>
          </div>

          {docSearch && (
            <div style={{ padding: '8px 20px', background: 'rgba(0, 212, 255, 0.04)', borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--cyan)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>
                Filtered to <strong>{filteredLineItems.length}</strong> matching row(s) for query "<strong>{docSearch}</strong>"
              </span>
              <button type="button" onClick={() => setDocSearch('')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12 }}>
                Clear Search
              </button>
            </div>
          )}

          <div className="table-container" style={{ border: 'none', borderRadius: 0, marginBottom: 0, maxHeight: isSplitView ? 'calc(100vh - 300px)' : undefined, overflowY: isSplitView ? 'auto' : undefined }}>
            <table className="quote-table">
              <thead>
                <tr>
                  {activeTemplateColumns.map(col => (
                    <th key={col.key} className={col.align === 'right' ? 'text-right' : ''} style={{ width: col.width, minWidth: col.minWidth }}>
                      {col.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredLineItems.length === 0 ? (
                  <tr>
                    <td colSpan={activeTemplateColumns.length} style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-secondary)' }}>
                      No line items found matching query "{docSearch}".
                    </td>
                  </tr>
                ) : (
                  filteredLineItems.map((item) => {
                    const isItemFlagged = item.needs_review
                    return (
                      <React.Fragment key={item.id}>
                        <tr className={isItemFlagged ? 'row-flagged' : ''}>
                          {activeTemplateColumns.map(col => {
                            if (col.key === 'page_no') {
                              const itemPage = item.page_no || 1
                              const isCurrentPage = activePage === itemPage
                              return (
                                <td key={col.key} style={{ textAlign: 'center' }}>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      setActivePage(itemPage)
                                      if (!isSplitView) setIsSplitView(true)
                                    }}
                                    style={{
                                      fontSize: 10,
                                      padding: '2px 7px',
                                      borderRadius: 4,
                                      fontWeight: 700,
                                      color: isCurrentPage ? 'var(--cyan)' : 'var(--text-secondary)',
                                      borderColor: isCurrentPage ? 'rgba(0, 212, 255, 0.4)' : 'rgba(255,255,255,0.1)',
                                      background: isCurrentPage ? 'rgba(0, 212, 255, 0.15)' : 'rgba(255,255,255,0.03)',
                                      cursor: 'pointer'
                                    }}
                                    title={`Click to jump original document preview to Page ${itemPage}`}
                                  >
                                    📄 Page {itemPage}
                                  </button>
                                </td>
                              )
                            }

                            const isEditing = editingCell?.itemId === item.id && editingCell?.fieldName === col.key
                            const rawVal = item[col.key]
                            
                            // Clean formatting: don't render cluttering 0s if field wasn't present
                            let formattedDisplay = rawVal
                            if (col.key === 'item_date') {
                              if (!rawVal && quotation.quotation_date) {
                                const d = new Date(quotation.quotation_date)
                                if (!isNaN(d.getTime())) {
                                  const mm = String(d.getMonth() + 1).padStart(2, '0')
                                  const dd = String(d.getDate()).padStart(2, '0')
                                  const yyyy = d.getFullYear()
                                  formattedDisplay = `${mm}/${dd}/${yyyy}`
                                }
                              }
                            } else if (rawVal === null || rawVal === undefined) {
                              formattedDisplay = ''
                            }

                            const isMismatched = (() => {
                               const qty = parseFloat(item.qty) || 0
                               const rate = parseFloat(item.rate) || 0
                               const gross = parseFloat(item.gross_amount) || 0
                               const discAmt = parseFloat(item.discount_amount) || 0
                               const taxable = parseFloat(item.taxable_amount) || 0
                               const cgstPct = parseFloat(item.cgst_pct) || 0
                               const cgst = parseFloat(item.cgst_amount) || 0
                               const sgstPct = parseFloat(item.sgst_pct) || 0
                               const sgst = parseFloat(item.sgst_amount) || 0
                               const finalVal = parseFloat(item.final_value) || 0

                               // 1. Gross Amount Mismatch (Qty * Rate != Gross)
                               if (col.key === 'gross_amount' && qty > 0 && rate > 0) {
                                 if (Math.abs((qty * rate) - gross) > 0.5) return true
                               }

                               // 2. Taxable Amount Mismatch (Gross - Discount != Taxable)
                               if (col.key === 'taxable_amount' && gross > 0 && discAmt > 0) {
                                 if (Math.abs((gross - discAmt) - taxable) > 0.5) return true
                               }

                               // 3. CGST Amount Mismatch (Taxable * CGST% != CGST Amt)
                               if (col.key === 'cgst_amount' && taxable > 0 && cgstPct > 0) {
                                 if (Math.abs((taxable * (cgstPct / 100)) - cgst) > 0.5) return true
                               }

                               // 4. SGST Amount Mismatch (Taxable * SGST% != SGST Amt)
                               if (col.key === 'sgst_amount' && taxable > 0 && sgstPct > 0) {
                                 if (Math.abs((taxable * (sgstPct / 100)) - sgst) > 0.5) return true
                               }

                               // 5. Final Value Mismatch (Taxable + CGST + SGST != Final)
                               if (col.key === 'final_value' && (taxable > 0 || gross > 0)) {
                                 const expectedFinal = (taxable > 0 ? taxable : gross) + cgst + sgst
                                 if (Math.abs(expectedFinal - finalVal) > 0.5) return true
                               }

                               // Flagged reason matching
                               if (item.needs_review && item.review_reason) {
                                 const reason = String(item.review_reason).toLowerCase()
                                 if (reason.includes(col.key.toLowerCase())) return true
                               }

                               return false
                             })()

                             return (
                               <td
                                 key={col.key}
                                 className={`${col.align === 'right' ? 'text-right' : ''} editable-cell ${isEditing ? 'editing' : ''}`}
                                 onClick={() => handleCellClick(item, col.key)}
                                 style={{
                                   fontWeight: col.key === 'final_value' ? 700 : (col.key === 'item_code' || col.key === 'line_no' ? 600 : 400),
                                   color: isMismatched ? '#ff4d6d' : (col.key === 'final_value' ? 'var(--cyan)' : (col.key === 'item_code' || col.key === 'line_no' ? '#fff' : undefined)),
                                   background: isMismatched ? 'rgba(244, 63, 94, 0.18)' : undefined,
                                   border: isMismatched ? '1px solid rgba(244, 63, 94, 0.6)' : undefined,
                                   whiteSpace: col.key === 'description' ? 'normal' : undefined
                                 }}
                                 title={isMismatched ? '⚠️ Unmatched Value: Mathematical discrepancy detected in line calculation!' : undefined}
                               >
                                 {isEditing ? (
                                   <input
                                     type="text"
                                     className={`cell-edit-input ${col.align === 'right' ? 'text-right' : ''}`}
                                     value={editValue}
                                     onChange={(e) => setEditValue(e.target.value)}
                                     onBlur={() => handleCellSave(item, col.key)}
                                     onKeyDown={(e) => handleKeyDown(e, item, col.key)}
                                     autoFocus
                                   />
                                 ) : (
                                   <HighlightMatch text={formattedDisplay} query={docSearch} />
                                 )}
                               </td>
                             )
                          })}
                        </tr>

                        {/* Display row review reason if flagged */}
                        {isItemFlagged && item.review_reason && (
                          <tr style={{ background: 'rgba(251, 191, 36, 0.05)' }}>
                            <td colSpan={activeTemplateColumns.length} style={{ padding: '6px 12px 10px 48px', fontSize: 12, color: 'var(--amber)' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <AlertTriangle size={14} />
                                <strong>Row Audit Warning:</strong> <HighlightMatch text={item.review_reason} query={docSearch} />
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
        </div>

      </div>
    </div>
  )
}
