import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { FileText, CheckCircle, AlertTriangle, Upload, ArrowRight, Clock, DollarSign, Activity, Layers, Search, ShieldCheck, Zap } from 'lucide-react'
import api from '../api/client.js'
import { useToast } from '../ToastContext.jsx'
import { formatIndianCurrency, formatDocumentType, getDocTypeColor, getFileFormat, getFileFormatBadgeStyle } from './QuotationsList.jsx'

function getPieArcPath(cx, cy, outerR, innerR, startAngleDeg, endAngleDeg) {
  let angleDiff = endAngleDeg - startAngleDeg
  if (angleDiff >= 360) angleDiff = 359.999
  if (angleDiff <= 0) return ''

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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const toast = useToast()

  const loadStats = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getStats()
      setStats(data)
    } catch (e) {
      setError(e.message)
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { loadStats() }, [loadStats])

  const totalDocs = stats.total_documents || 1

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
        
        {/* Card 1: Total Documents Ingested */}
        <Link
          to="/quotations"
          className="card kpi-card-interactive"
          style={{
            padding: 20,
            background: 'linear-gradient(135deg, rgba(0,212,255,0.08) 0%, rgba(15,23,42,0.8) 100%)',
            border: '1px solid rgba(0,212,255,0.25)',
            textDecoration: 'none',
            color: 'inherit',
            display: 'block',
            transition: 'all 0.25s ease-in-out',
            cursor: 'pointer'
          }}
          title="Click to view all ingested documents in Explorer"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600, display: 'block' }}>Total Ingested</span>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#fff', marginTop: 4 }}>
                {loading ? '...' : stats.total_documents}
              </div>
            </div>
            <div style={{ width: 42, height: 42, borderRadius: 10, background: 'rgba(0,212,255,0.15)', color: 'var(--cyan)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(0,212,255,0.3)' }}>
              <FileText size={20} />
            </div>
          </div>
          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--cyan)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Zap size={12} /> 100% Ingestion Active
            </span>
            <ArrowRight size={13} style={{ opacity: 0.7 }} />
          </div>
        </Link>

        {/* Card 2: Extracted Invoices & Billing Docs */}
        <Link
          to="/quotations?type=invoice"
          className="card kpi-card-interactive"
          style={{
            padding: 20,
            background: 'linear-gradient(135deg, rgba(34,197,94,0.08) 0%, rgba(15,23,42,0.8) 100%)',
            border: '1px solid rgba(34,197,94,0.25)',
            textDecoration: 'none',
            color: 'inherit',
            display: 'block',
            transition: 'all 0.25s ease-in-out',
            cursor: 'pointer'
          }}
          title="Click to filter Invoices & Billing Documents"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600, display: 'block' }}>Invoices & Billing Docs</span>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#fff', marginTop: 4 }}>
                {loading ? '...' : (stats.extracted_invoices || stats.total_documents)}
              </div>
            </div>
            <div style={{ width: 42, height: 42, borderRadius: 10, background: 'rgba(34,197,94,0.15)', color: 'var(--green)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(34,197,94,0.3)' }}>
              <CheckCircle size={20} />
            </div>
          </div>
          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--green)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <ShieldCheck size={12} /> Filter Tax Invoices & POs
            </span>
            <ArrowRight size={13} style={{ opacity: 0.7 }} />
          </div>
        </Link>

        {/* Card 3: Financial Value Processed */}
        <Link
          to="/quotations"
          className="card kpi-card-interactive"
          style={{
            padding: 20,
            background: 'linear-gradient(135deg, rgba(168,85,247,0.08) 0%, rgba(15,23,42,0.8) 100%)',
            border: '1px solid rgba(168,85,247,0.25)',
            textDecoration: 'none',
            color: 'inherit',
            display: 'block',
            transition: 'all 0.25s ease-in-out',
            cursor: 'pointer'
          }}
          title="Click to view all financial line items in Explorer"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600, display: 'block' }}>Financial Value Processed</span>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginTop: 6, letterSpacing: '-0.02em' }}>
                {loading ? '...' : formatIndianCurrency(stats.total_value_extracted)}
              </div>
            </div>
            <div style={{ width: 42, height: 42, borderRadius: 10, background: 'rgba(168,85,247,0.15)', color: 'var(--purple)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(168,85,247,0.3)' }}>
              <DollarSign size={20} />
            </div>
          </div>
          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--purple)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Activity size={12} /> Reconciled Net Volume
            </span>
            <ArrowRight size={13} style={{ opacity: 0.7 }} />
          </div>
        </Link>

        {/* Card 4: Audit Quarantine Queue */}
        <Link
          to="/quotations?status=needs_review"
          className="card kpi-card-interactive"
          style={{
            padding: 20,
            background: 'linear-gradient(135deg, rgba(251,191,36,0.08) 0%, rgba(15,23,42,0.8) 100%)',
            border: stats.quarantined_count > 0 ? '1px solid rgba(251,191,36,0.5)' : '1px solid rgba(251,191,36,0.25)',
            textDecoration: 'none',
            color: 'inherit',
            display: 'block',
            transition: 'all 0.25s ease-in-out',
            cursor: 'pointer'
          }}
          title="Click to view Quarantine Audit Queue"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600, display: 'block' }}>Audit Quarantine Queue</span>
              <div style={{ fontSize: 28, fontWeight: 800, color: stats.quarantined_count > 0 ? 'var(--amber)' : '#fff', marginTop: 4 }}>
                {loading ? '...' : stats.quarantined_count}
              </div>
            </div>
            <div style={{ width: 42, height: 42, borderRadius: 10, background: 'rgba(251,191,36,0.15)', color: 'var(--amber)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(251,191,36,0.3)' }}>
              <AlertTriangle size={20} />
            </div>
          </div>
          <div style={{ marginTop: 12, fontSize: 11, color: stats.quarantined_count > 0 ? 'var(--amber)' : 'var(--text-muted)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>
              {stats.quarantined_count > 0 ? 'Requires Line Item Audit' : 'Zero Flagged Discrepancies'}
            </span>
            <ArrowRight size={13} style={{ opacity: 0.7 }} />
          </div>
        </Link>
      </div>

      {/* Document Type Distribution Pie Chart Card */}
      {stats.by_type && Object.keys(stats.by_type).length > 0 && (() => {
        const entries = Object.entries(stats.by_type)
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

        const activeItem = hoveredSlice

        return (
          <div className="card mb-4" style={{ padding: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 12 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8, color: '#fff' }}>
                <Layers size={18} style={{ color: 'var(--cyan)' }} /> Document Type Distribution
              </h3>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600 }}>
                {entries.length} Classification Categories
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 36, flexWrap: 'wrap' }}>
              {/* Left Column: Interactive SVG Donut / Pie Chart */}
              <div style={{ position: 'relative', width: 280, height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, margin: 'auto' }}>
                <svg width="280" height="280" viewBox="0 0 300 300" style={{ overflow: 'visible' }}>
                  {pieSlices.map((slice) => {
                    const isHovered = hoveredSlice?.type === slice.type
                    const outerR = isHovered ? 138 : 128
                    const innerR = isHovered ? 74 : 80
                    const pathData = getPieArcPath(150, 150, outerR, innerR, slice.startAngle, slice.endAngle)

                    return (
                      <g key={slice.type} style={{ cursor: 'pointer' }}>
                        <path
                          d={pathData}
                          fill={slice.color}
                          opacity={hoveredSlice ? (isHovered ? 1 : 0.45) : 0.95}
                          style={{ transition: 'all 0.2s ease-in-out' }}
                          onMouseEnter={() => setHoveredSlice(slice)}
                          onMouseLeave={() => setHoveredSlice(null)}
                          onClick={() => window.location.href = `/quotations?type=${slice.type}`}
                        />
                      </g>
                    )
                  })}
                </svg>

                {/* Center Content Inside Donut */}
                <div style={{ position: 'absolute', textAlign: 'center', pointerEvents: 'none', padding: '0 12px' }}>
                  <div style={{ fontSize: 32, fontWeight: 800, color: activeItem ? activeItem.color : '#fff', lineHeight: 1.1 }}>
                    {activeItem ? activeItem.count : totalCount}
                  </div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', marginTop: 6, letterSpacing: '0.04em' }}>
                    {activeItem ? activeItem.label : 'Total Documents'}
                  </div>
                  {activeItem && (
                    <div style={{ fontSize: 14, fontWeight: 800, color: activeItem.color, marginTop: 4 }}>
                      {activeItem.pct}%
                    </div>
                  )}
                </div>
              </div>

              {/* Right Column: Interactive Category Legend Grid */}
              <div style={{ flex: 1, minWidth: 260, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                {pieSlices.map((slice) => {
                  const isHovered = hoveredSlice?.type === slice.type
                  return (
                    <Link
                      key={slice.type}
                      to={`/quotations?type=${slice.type}`}
                      className="kpi-card-interactive"
                      onMouseEnter={() => setHoveredSlice(slice)}
                      onMouseLeave={() => setHoveredSlice(null)}
                      style={{
                        background: isHovered ? 'rgba(255, 255, 255, 0.05)' : 'rgba(255, 255, 255, 0.02)',
                        border: isHovered ? `1px solid ${slice.color}` : '1px solid var(--border)',
                        borderRadius: 10,
                        padding: '12px 14px',
                        textDecoration: 'none',
                        color: 'inherit',
                        transition: 'all 0.2s ease',
                        display: 'flex',
                        flexDirection: 'column',
                        justify: 'space-between'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                        <span style={{ width: 9, height: 9, borderRadius: '50%', background: slice.color }}></span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: '#fff', textTransform: 'uppercase', letterSpacing: '0.02em' }}>
                          {slice.label}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                        <span style={{ fontSize: 20, fontWeight: 800, color: '#fff' }}>{slice.count}</span>
                        <span style={{ fontSize: 13, fontWeight: 800, color: slice.color }}>{slice.pct}%</span>
                      </div>
                    </Link>
                  )
                })}
              </div>
            </div>
          </div>
        )
      })()}

      {/* Recently Processed Documents List */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Clock size={16} style={{ color: 'var(--cyan)' }} /> Recently Ingested Documents
          </h3>
          <Link to="/quotations" className="btn btn-ghost btn-sm" style={{ color: 'var(--cyan)' }}>
            View Explorer Directory <ArrowRight size={13} />
          </Link>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: 'center' }}><div className="spinner" style={{ margin: 'auto' }} /></div>
        ) : !stats.recent_documents || stats.recent_documents.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No recent documents</div>
        ) : (
          <div className="table-container" style={{ border: 'none', borderRadius: 0, marginBottom: 0 }}>
            <table className="quote-table">
              <thead>
                <tr>
                  <th>Format</th>
                  <th>Doc / Ref #</th>
                  <th>Doc Type</th>
                  <th>Vendor / Hospital</th>
                  <th>Customer / Patient</th>
                  <th>Doc Date</th>
                  <th className="text-right">Grand Total</th>
                  <th>Audit Status</th>
                  <th className="text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent_documents.map((doc) => {
                  const format = getFileFormat(doc.source_file)
                  return (
                    <tr key={doc.id || doc.document_id}>
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
                        <span style={{ 
                          color: getDocTypeColor(doc.document_type), 
                          fontWeight: 700, 
                          fontSize: 10, 
                          textTransform: 'uppercase',
                          background: `${getDocTypeColor(doc.document_type)}1A`,
                          padding: '2px 6px',
                          borderRadius: 4
                        }}>
                          {formatDocumentType(doc.document_type)}
                        </span>
                      </td>
                      <td>{doc.vendor_name || 'N/A'}</td>
                      <td>{doc.customer_name || 'N/A'}</td>
                      <td>
                        {doc.document_date ? new Date(doc.document_date).toLocaleDateString('en-IN', {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric'
                        }) : 'N/A'}
                      </td>
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
