import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { FileText, CheckCircle, AlertTriangle, Upload, ArrowRight, Clock, DollarSign, Activity, Layers, Search, ShieldCheck, Zap } from 'lucide-react'
import api from '../api/client.js'
import quotationApi from '../api/quotationClient.js'
import { useToast } from '../ToastContext.jsx'
import { formatIndianCurrency, formatDocumentType, getDocTypeColor, getFileFormat, getFileFormatBadgeStyle, formatDisplayDate } from './QuotationsList.jsx'

function getPieArcPath(cx, cy, outerR, innerR, startAngleDeg, endAngleDeg) {
  let angleDiff = endAngleDeg - startAngleDeg
  if (isNaN(angleDiff) || angleDiff <= 0) return ''
  if (angleDiff >= 360) angleDiff = 359.999

  const actualEndAngle = startAngleDeg + angleDiff

  const startRad = ((startAngleDeg - 90) * Math.PI) / 180
  const endRad = ((actualEndAngle - 90) * Math.PI) / 180

  const x1 = cx + outerR * Math.cos(startRad)
  const y1 = cy + outerR * Math.sin(startRad)
  const x2 = cx + outerR * Math.cos(endRad)
  const y2 = cy + outerR * Math.sin(endRad)

  const x3 = cx + innerR * Math.cos(endRad)
  const y3 = cy + innerR * Math.sin(endRad)
  const x4 = cx + innerR * Math.cos(startRad)
  const y4 = cy + innerR * Math.sin(startRad)

  const largeArc = angleDiff > 180 ? 1 : 0

  return `M ${x1} ${y1} A ${outerR} ${outerR} 0 ${largeArc} 1 ${x2} ${y2} L ${x3} ${y3} A ${innerR} ${innerR} 0 ${largeArc} 0 ${x4} ${y4} Z`
}

export default function Dashboard() {
  const [stats, setStats] = useState({ total_documents: 0, total_value_extracted: 0, extracted_invoices: 0, by_type: {}, quarantined_count: 0, recent_documents: [] })
  const [hoveredSlice, setHoveredSlice] = useState(null)
  const [selectedType, setSelectedType] = useState(null)
  const [displayedDocuments, setDisplayedDocuments] = useState([])
  const [tableLoading, setTableLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const toast = useToast()

  const loadStats = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getStats()
      setStats(data || {})
      setDisplayedDocuments(data?.recent_documents || [])
    } catch (e) {
      setError(e.message)
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { loadStats() }, [loadStats])

  // Fetch documents for the selected category from API
  useEffect(() => {
    if (!selectedType) {
      setDisplayedDocuments(stats.recent_documents || [])
      return
    }

    let isMounted = true
    setTableLoading(true)
    quotationApi.listQuotations({ document_type: selectedType, limit: 15 })
      .then(data => {
        if (isMounted) {
          const formatted = (data?.items || []).map(d => ({
            id: d.id,
            document_no: d.quotation_no || d.document_no,
            document_type: d.document_type,
            document_date: d.quotation_date || d.document_date,
            grand_total_final: d.grand_total_final,
            extraction_status: d.extraction_status,
            source_file: d.source_file,
            vendor_name: d.vendor_name,
            customer_name: d.customer_name
          }))
          setDisplayedDocuments(formatted)
          setTableLoading(false)
        }
      })
      .catch(err => {
        if (isMounted) setTableLoading(false)
      })

    return () => { isMounted = false }
  }, [selectedType, stats.recent_documents])


  const totalDocs = stats.total_documents || 1

  const entries = stats.by_type ? Object.entries(stats.by_type) : []
  let currentAngle = 0
  const totalCount = stats.total_documents || entries.reduce((acc, [, c]) => acc + c, 0) || 1

  const pieSlices = entries.map(([type, count]) => {
    const pct = (count / totalCount) * 100
    const startAngle = currentAngle
    const endAngle = currentAngle + (pct / 100) * 360
    currentAngle = endAngle
    const color = getDocTypeColor(type)
    return {
      type,
      count,
      pct: pct.toFixed(1),
      startAngle,
      endAngle,
      color,
      label: formatDocumentType(type)
    }
  })

  const activeItem = hoveredSlice || (selectedType ? pieSlices.find(s => s.type === selectedType) : null)


  return (
    <div>
      {/* Top Welcome Header */}
      <div className="mb-4 flex items-center justify-between" style={{ flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>Executive Processing Dashboard</h1>
            <span style={{ fontSize: 11, background: 'rgba(34, 197, 94, 0.15)', color: 'var(--green)', padding: '3px 10px', borderRadius: 20, border: '1px solid rgba(34, 197, 94, 0.3)', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)', display: 'inline-block' }}></span>
              Engine Online
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
            Real-time scanner metrics, financial volume extracted, and OCR document breakdown
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Link to="/quotations" className="btn btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <Search size={15} /> Explore Database
          </Link>
          <Link to="/upload" className="btn btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <Upload size={15} /> Ingest New Document
          </Link>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div style={{ background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', borderRadius: 8, padding: 14, color: '#f43f5e', fontSize: 13, marginBottom: 20 }}>
          ⚠ Failed to load live dashboard stats: {error}
        </div>
      )}

      {/* Interactive KPI Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
        
        <Link
          to="/quotations"
          className="card kpi-card-interactive"
          style={{
            padding: 20,
            background: 'var(--kpi-gradient-1)',
            border: '1px solid rgba(0,212,255,0.25)',
            textDecoration: 'none',
            color: 'inherit',
            display: 'block'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--cyan)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Ingested</span>
            <div style={{ background: 'rgba(0,212,255,0.15)', padding: 8, borderRadius: 8 }}>
              <FileText size={18} style={{ color: 'var(--cyan)' }} />
            </div>
          </div>
          <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1 }}>{stats.total_documents}</div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
            <span>Archived Documents</span>
            <ArrowRight size={13} style={{ opacity: 0.7 }} />
          </div>
        </Link>

        <div
          className="card"
          style={{
            padding: 20,
            background: 'var(--kpi-gradient-2)',
            border: '1px solid rgba(34,197,94,0.25)'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--green)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Extracted Value</span>
            <div style={{ background: 'rgba(34,197,94,0.15)', padding: 8, borderRadius: 8 }}>
              <DollarSign size={18} style={{ color: 'var(--green)' }} />
            </div>
          </div>
          <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.2 }}>
            {formatIndianCurrency(stats.total_value_extracted)}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
            <span>Audited & Reconciled Sum</span>
            <ShieldCheck size={13} style={{ color: 'var(--green)', opacity: 0.8 }} />
          </div>
        </div>

        <Link
          to="/quotations?status=ok"
          className="card kpi-card-interactive"
          style={{
            padding: 20,
            background: 'var(--kpi-gradient-3)',
            border: '1px solid rgba(168,85,247,0.25)',
            textDecoration: 'none',
            color: 'inherit',
            display: 'block'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#c084fc', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Verified Invoices</span>
            <div style={{ background: 'rgba(168,85,247,0.15)', padding: 8, borderRadius: 8 }}>
              <CheckCircle size={18} style={{ color: '#c084fc' }} />
            </div>
          </div>
          <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1 }}>{stats.extracted_invoices}</div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
            <span>{totalDocs > 0 ? ((stats.extracted_invoices / totalDocs) * 100).toFixed(0) : 0}% Ingestion Accuracy</span>
            <ArrowRight size={13} style={{ opacity: 0.7 }} />
          </div>
        </Link>

        <Link
          to="/quotations?status=needs_review"
          className="card kpi-card-interactive"
          style={{
            padding: 20,
            background: stats.quarantined_count > 0 ? 'var(--kpi-gradient-4)' : 'var(--bg-card)',
            border: stats.quarantined_count > 0 ? '1px solid rgba(245,158,11,0.35)' : '1px solid var(--border)',
            textDecoration: 'none',
            color: 'inherit',
            display: 'block'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--amber)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Needs Review</span>
            <div style={{ background: 'rgba(245,158,11,0.15)', padding: 8, borderRadius: 8 }}>
              <AlertTriangle size={18} style={{ color: 'var(--amber)' }} />
            </div>
          </div>
          <div style={{ fontSize: 32, fontWeight: 800, color: stats.quarantined_count > 0 ? 'var(--amber)' : 'var(--text-primary)', lineHeight: 1 }}>
            {stats.quarantined_count}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
            <span>{stats.quarantined_count > 0 ? 'Human Audit Required' : 'Zero Discrepancies'}</span>
            <ArrowRight size={13} style={{ opacity: 0.7 }} />
          </div>
        </Link>
      </div>


      {/* Document Type Distribution Interactive Wheel & Legend Card */}
      {pieSlices.length > 0 && (
        <div className="card mb-4" style={{ padding: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8, color: '#fff' }}>
                <Layers size={18} style={{ color: 'var(--cyan)' }} /> Document Type Distribution
              </h3>
              {selectedType && (
                <span style={{
                  fontSize: 11,
                  background: 'rgba(0, 212, 255, 0.12)',
                  color: 'var(--cyan)',
                  padding: '2px 8px',
                  borderRadius: 12,
                  border: '1px solid rgba(0, 212, 255, 0.3)',
                  fontWeight: 700
                }}>
                  Filtered: {formatDocumentType(selectedType)}
                </span>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              {selectedType && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => { setSelectedType(null); setHoveredSlice(null); }}
                  style={{ fontSize: 11, padding: '3px 8px', color: 'var(--text-muted)' }}
                >
                  Reset Filter
                </button>
              )}
              <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600 }}>
                {entries.length} Classification Categories
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 36, flexWrap: 'wrap' }}>
            {/* Left Column: Interactive SVG Donut Wheel Chart */}
            <div style={{ position: 'relative', width: 280, height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, margin: 'auto' }}>
              <svg width="280" height="280" viewBox="0 0 300 300" style={{ overflow: 'visible' }}>
                {pieSlices.map((slice) => {
                  const isHovered = activeItem?.type === slice.type
                  const isSelected = selectedType === slice.type
                  const outerR = (isHovered || isSelected) ? 140 : 128
                  const innerR = (isHovered || isSelected) ? 72 : 80
                  const pathData = getPieArcPath(150, 150, outerR, innerR, slice.startAngle, slice.endAngle)

                  return (
                    <g key={slice.type} style={{ cursor: 'pointer' }}>
                      <path
                        d={pathData}
                        fill={slice.color}
                        opacity={activeItem ? ((isHovered || isSelected) ? 1 : 0.35) : 0.95}
                        style={{
                          transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                          filter: (isHovered || isSelected) ? `drop-shadow(0 0 8px ${slice.color}66)` : 'none'
                        }}
                        onMouseEnter={() => setHoveredSlice(slice)}
                        onMouseLeave={() => setHoveredSlice(null)}
                        onClick={() => setSelectedType(prev => prev === slice.type ? null : slice.type)}
                      />
                    </g>
                  )
                })}
              </svg>

              {/* Center Content Inside Donut */}
              <div
                style={{
                  position: 'absolute',
                  textAlign: 'center',
                  cursor: 'pointer',
                  padding: '0 12px',
                  userSelect: 'none'
                }}
                onClick={() => { setSelectedType(null); setHoveredSlice(null); }}
              >
                <div style={{ fontSize: 32, fontWeight: 800, color: activeItem ? activeItem.color : '#fff', lineHeight: 1.1, transition: 'color 0.2s ease' }}>
                  {activeItem ? activeItem.count : totalCount}
                </div>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', marginTop: 6, letterSpacing: '0.04em' }}>
                  {activeItem ? activeItem.label : 'Total Documents'}
                </div>
                <div style={{ fontSize: 13, fontWeight: 800, color: activeItem ? activeItem.color : 'var(--cyan)', marginTop: 4 }}>
                  {activeItem ? `${activeItem.pct}%` : '100%'}
                </div>
              </div>
            </div>

            {/* Right Column: Interactive Category Legend Grid */}
            <div style={{ flex: 1, minWidth: 260, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
              {pieSlices.map((slice) => {
                const isHovered = hoveredSlice?.type === slice.type
                const isSelected = selectedType === slice.type
                return (
                  <div
                    key={slice.type}
                    role="button"
                    tabIndex={0}
                    className="kpi-card-interactive"
                    onMouseEnter={() => setHoveredSlice(slice)}
                    onMouseLeave={() => setHoveredSlice(null)}
                    onClick={() => setSelectedType(prev => prev === slice.type ? null : slice.type)}
                    style={{
                      background: isSelected ? `${slice.color}15` : (isHovered ? 'rgba(255, 255, 255, 0.05)' : 'rgba(255, 255, 255, 0.02)'),
                      border: isSelected ? `2px solid ${slice.color}` : (isHovered ? `1px solid ${slice.color}` : '1px solid var(--border)'),
                      borderRadius: 10,
                      padding: '12px 14px',
                      color: 'inherit',
                      transition: 'all 0.2s ease',
                      display: 'flex',
                      flexDirection: 'column',
                      justify: 'space-between',
                      cursor: 'pointer',
                      boxShadow: isSelected ? `0 0 12px ${slice.color}33` : 'none'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ width: 9, height: 9, borderRadius: '50%', background: slice.color }}></span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: '#fff', textTransform: 'uppercase', letterSpacing: '0.02em' }}>
                          {slice.label}
                        </span>
                      </div>
                      {isSelected && (
                        <span style={{ fontSize: 9, background: slice.color, color: '#000', padding: '1px 5px', borderRadius: 4, fontWeight: 800 }}>
                          ACTIVE
                        </span>
                      )}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <span style={{ fontSize: 20, fontWeight: 800, color: '#fff' }}>{slice.count}</span>
                      <span style={{ fontSize: 13, fontWeight: 800, color: slice.color }}>{slice.pct}%</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Recently Processed Documents List Synchronized with Wheel */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Clock size={16} style={{ color: 'var(--cyan)' }} /> 
              {selectedType ? `Recently Ingested (${formatDocumentType(selectedType)})` : 'Recently Ingested Documents'}
            </h3>
            <span style={{ fontSize: 11, background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-secondary)', padding: '2px 8px', borderRadius: 10 }}>
              {displayedDocuments.length} shown
            </span>

          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {selectedType && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setSelectedType(null)}
                style={{ fontSize: 11, padding: '3px 8px', color: 'var(--cyan)' }}
              >
                Show All Types
              </button>
            )}
            <Link to={selectedType ? `/quotations?type=${selectedType}` : '/quotations'} className="btn btn-ghost btn-sm" style={{ color: 'var(--cyan)' }}>
              View Explorer Directory <ArrowRight size={13} />
            </Link>
          </div>
        </div>

        {(loading || tableLoading) ? (
          <div style={{ padding: 40, textAlign: 'center' }}><div className="spinner" style={{ margin: 'auto' }} /></div>
        ) : displayedDocuments.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            No documents found for this category.{' '}
            {selectedType && (
              <button onClick={() => setSelectedType(null)} className="btn btn-ghost btn-sm" style={{ color: 'var(--cyan)', marginLeft: 8 }}>
                Clear Filter
              </button>
            )}
          </div>
        ) : (
          <div className="table-container" style={{ border: 'none', borderRadius: 0, marginBottom: 0 }}>
            <table className="quote-table">
              <thead>
                <tr>
                  <th>Format</th>
                  <th>Doc / Ref #</th>
                  <th>Doc Type</th>
                  <th>Vendor</th>
                  <th>Customer / Patient</th>
                  <th>Doc Date</th>
                  <th className="text-right">Grand Total</th>
                  <th>Audit Status</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {displayedDocuments.map((doc) => {
                  const format = getFileFormat(doc.source_file)
                  const isHoveredInTable = activeItem?.type === doc.document_type
                  return (
                    <tr
                      key={doc.id || doc.document_id}
                      onMouseEnter={() => {
                        const s = pieSlices.find(sl => sl.type === doc.document_type)
                        if (s) setHoveredSlice(s)
                      }}
                      onMouseLeave={() => setHoveredSlice(null)}
                      style={{
                        background: isHoveredInTable ? `${getDocTypeColor(doc.document_type)}0D` : 'transparent',
                        transition: 'background 0.15s ease'
                      }}
                    >

                      <td>
                        <span style={{
                          fontSize: 10,
                          fontWeight: 700,
                          padding: '2px 6px',
                          borderRadius: 4,
                          letterSpacing: '0.04em',
                          ...getFileFormatBadgeStyle(format)
                        }}>
                          {format}
                        </span>
                      </td>
                      <td style={{ fontWeight: 600, color: '#fff' }}>
                        {doc.document_no || `Doc #${doc.id || doc.document_id}`}
                      </td>
                      <td>
                        <span
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedType(prev => prev === doc.document_type ? null : doc.document_type);
                          }}
                          style={{ 
                            color: getDocTypeColor(doc.document_type), 
                            fontWeight: 700, 
                            fontSize: 10, 
                            textTransform: 'uppercase',
                            background: `${getDocTypeColor(doc.document_type)}1A`,
                            padding: '2px 6px',
                            borderRadius: 4,
                            cursor: 'pointer'
                          }}
                          title="Click to filter by this document type"
                        >
                          {formatDocumentType(doc.document_type)}
                        </span>
                      </td>
                      <td>{doc.vendor_name || 'N/A'}</td>
                      <td>{doc.customer_name || 'N/A'}</td>
                      <td>{formatDisplayDate(doc.document_date)}</td>
                      <td className="text-right" style={{ fontWeight: 700, color: 'var(--cyan)' }}>

                        {formatIndianCurrency(doc.grand_total_final)}
                      </td>
                      <td>
                        <span className={`badge badge-${doc.extraction_status || 'ok'}`}>
                          <span className="badge-dot" />
                          {doc.extraction_status === 'needs_review' ? 'Needs Review' : 'Ok'}
                        </span>
                      </td>
                      <td className="text-right">
                        <Link to={`/quotations/${doc.id || doc.document_id}`} className="btn btn-secondary btn-sm" style={{ padding: '3px 10px', fontSize: 11 }}>
                          Audit
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
