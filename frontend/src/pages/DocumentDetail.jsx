import React, { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, FileText, Building2, CheckCircle, Tag, Layers } from 'lucide-react'
import api from '../api/client.js'
import { useToast } from '../ToastContext.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import VendorSelector from '../components/VendorSelector.jsx'

export default function DocumentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [doc, setDoc] = useState(null)
  const [vendorDetail, setVendorDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadDocumentDetail = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getDocument(id)
      setDoc(data)

      if (data && data.vendor_id) {
        try {
          const v = await api.getVendorById(data.vendor_id)
          setVendorDetail(v)
        } catch (e) {
          // Vendor missing
        }
      }
    } catch (e) {
      setError(e.message)
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [id, toast])

  useEffect(() => { loadDocumentDetail() }, [loadDocumentDetail])

  const handleLinkVendor = async (vendorId) => {
    try {
      await api.linkVendorToDocument(id, vendorId)
      toast('Vendor linked to document successfully!', 'success')
      loadDocumentDetail()
    } catch (e) {
      toast(`Failed to link vendor: ${e.message}`, 'error')
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <div className="spinner" style={{ margin: 'auto' }} />
        <div style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: 13 }}>Loading document detail...</div>
      </div>
    )
  }

  if (error || !doc) {
    return (
      <div>
        <button className="btn btn-secondary btn-sm mb-3" onClick={() => navigate('/documents')}>
          <ArrowLeft size={13} /> Back to Documents
        </button>
        <div className="card" style={{ padding: 32, color: '#f43f5e', background: 'rgba(244,63,94,0.1)', border: '1px solid rgba(244,63,94,0.3)' }}>
          ⚠ {error || 'Document not found.'}
        </div>
      </div>
    )
  }

  const fields = doc.fields || {}
  const fieldEntries = Object.entries(fields)

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/documents')}>
            <ArrowLeft size={13} /> Back
          </button>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>ID: {id}</span>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={loadDocumentDetail}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Header Info Card */}
      <div className="card mb-4" style={{ background: 'rgba(0, 212, 255, 0.03)', border: '1px solid rgba(0, 212, 255, 0.2)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <FileText size={22} style={{ color: 'var(--cyan)' }} />
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: '#fff' }}>{doc.original_filename || id}</h2>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                Uploaded: {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleString() : '—'}
              </div>
            </div>
          </div>
          <StatusBadge status={doc.status} />
        </div>

        <div style={{ display: 'flex', gap: 20, fontSize: 12, color: '#ccc', paddingTop: 10, borderTop: '1px solid var(--border)' }}>
          <div>Classification: <strong style={{ color: 'var(--cyan)', textTransform: 'capitalize' }}>{doc.document_type || 'generic'}</strong></div>
          <div>Confidence: <strong style={{ color: 'var(--green)' }}>{doc.confidence ? `${(doc.confidence * 100).toFixed(0)}%` : '100%'}</strong></div>
          <div>File Type: <strong style={{ textTransform: 'uppercase' }}>{doc.file_type || 'pdf'}</strong></div>
        </div>
      </div>

      {/* Vendor Section */}
      <div className="card mb-4" style={{ padding: 18 }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 10px 0', color: 'var(--cyan)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Building2 size={16} /> Linked Vendor Details
        </h3>
        {vendorDetail ? (
          <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: 12, border: '1px solid var(--border)', marginBottom: 12 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>{vendorDetail.vendor_name}</div>
            <div style={{ fontSize: 12, color: '#aaa', marginTop: 4 }}>📍 {vendorDetail.address || 'No address registered'}</div>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>No vendor linked to this document yet.</div>
        )}

        {/* Vendor Selector Component */}
        <VendorSelector />
      </div>

      {/* Extracted Fields Rendered List */}
      <div className="card" style={{ padding: 20 }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 16px 0', color: 'var(--cyan)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Layers size={16} /> Clean Extracted Label / Value Fields
        </h3>

        {fieldEntries.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No extracted fields stored for this document.</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
            {fieldEntries.map(([name, value]) => (
              <div key={name} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 14px' }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--cyan)', textTransform: 'uppercase', marginBottom: 4 }}>
                  {name.replace(/_/g, ' ')}
                </div>
                <div style={{ fontSize: 13, color: '#fff', fontFamily: "'JetBrains Mono', monospace", wordBreak: 'break-all' }}>
                  {String(value)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
