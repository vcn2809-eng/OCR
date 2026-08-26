import React, { useState, useEffect, useCallback } from 'react'
import { AlertTriangle, CheckCircle, XCircle, RefreshCw, Edit3, Save, X, Search } from 'lucide-react'
import api from '../api/client.js'
import { useToast } from '../ToastContext.jsx'
import GhostSearchInput from '../components/GhostSearchInput.jsx'

export default function QuarantinePage() {
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  // Inline Field Editor state
  const [editingItemId, setEditingItemId] = useState(null)
  const [editedRecord, setEditedRecord] = useState({})

  const toast = useToast()

  const loadQuarantine = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.listQuarantine(1, 100)
      setItems(res.items || [])
      setTotal(res.total || 0)
    } catch (e) {
      setError(e.message)
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { loadQuarantine() }, [loadQuarantine])

  const handleStartEdit = (item) => {
    setEditingItemId(item.id)
    setEditedRecord(item.record || {})
  }

  const handleFieldChange = (key, val) => {
    setEditedRecord(prev => ({ ...prev, [key]: val }))
  }

  const handleApproveWithEdits = async (id) => {
    try {
      await api.resolveQuarantine(id, 'accept', editedRecord)
      toast(`Quarantine item ${id} approved and moved into documents properly!`, 'success')
      setEditingItemId(null)
      loadQuarantine()
    } catch (e) {
      toast(`Failed to approve: ${e.message}`, 'error')
    }
  }

  const handleDismiss = async (id) => {
    try {
      await api.resolveQuarantine(id, 'dismiss')
      toast(`Quarantine item ${id} dismissed`, 'success')
      loadQuarantine()
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const filteredItems = items.filter(item => {
    if (!searchQuery || !searchQuery.trim()) return true
    const q = searchQuery.toLowerCase().trim()
    const docIdMatch = String(item.document_id || '').toLowerCase().includes(q)
    const idMatch = String(item.id || '').toLowerCase().includes(q)
    const typeMatch = String(item.document_type || '').toLowerCase().includes(q)
    const reasonMatch = (Array.isArray(item.reasons) ? item.reasons.join(' ') : String(item.reasons || '')).toLowerCase().includes(q)
    const recordMatch = JSON.stringify(item.record || {}).toLowerCase().includes(q)
    return docIdMatch || idMatch || typeMatch || reasonMatch || recordMatch
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-4" style={{ flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>Quarantine Review</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
            {total} records flagged for low confidence or schema validation errors
          </p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button className="btn btn-secondary btn-sm" onClick={loadQuarantine} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {/* Search Input Bar */}
      <div className="mb-4" style={{ maxWidth: 500 }}>
        <GhostSearchInput
          value={searchQuery}
          onChange={(val) => setSearchQuery(val)}
          placeholder="Search quarantine items by Doc ID, vendor, field values, or reason..."
        />
      </div>

      {/* Filtered count status indicator */}
      {searchQuery && (
        <div style={{ padding: '8px 14px', background: 'rgba(0,212,255,0.05)', border: '1px solid rgba(0,212,255,0.2)', borderRadius: 6, fontSize: 12, color: 'var(--cyan)', marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Showing <strong>{filteredItems.length}</strong> of {items.length} quarantined record(s) matching "<strong>{searchQuery}</strong>"</span>
          <button type="button" onClick={() => setSearchQuery('')} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12 }}>
            Clear Search
          </button>
        </div>
      )}

      {/* Explicit Error State */}
      {error && (
        <div style={{ background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', borderRadius: 8, padding: 14, color: '#f43f5e', fontSize: 13, marginBottom: 16 }}>
          ⚠ Error loading quarantine list: {error}
        </div>
      )}

      {loading ? (
        <div className="card" style={{ padding: 48, textAlign: 'center' }}>
          <div className="spinner" style={{ margin: 'auto' }} />
          <div style={{ marginTop: 12, color: 'var(--text-muted)', fontSize: 13 }}>Loading quarantine items...</div>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="card" style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>
          {searchQuery ? `No quarantined records found matching "${searchQuery}".` : 'No quarantined records awaiting review.'}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {filteredItems.map((item) => {
            const isEditing = editingItemId === item.id
            const currentRecord = isEditing ? editedRecord : (item.record || {})

            return (
              <div key={item.id} className="card" style={{ border: '1px solid rgba(251, 191, 36, 0.3)', background: 'rgba(251, 191, 36, 0.02)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <AlertTriangle size={18} style={{ color: 'var(--amber)' }} />
                    <span style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>Doc ID: {item.document_id || item.id}</span>
                    <span className="badge" style={{ background: 'rgba(251, 191, 36, 0.15)', color: 'var(--amber)', fontSize: 11, textTransform: 'capitalize' }}>
                      {item.document_type || 'unclassified'}
                    </span>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    Flagged: {item.flagged_at ? new Date(item.flagged_at).toLocaleString() : '—'}
                  </span>
                </div>

                {/* Flagged Reasons */}
                <div style={{ background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.2)', borderRadius: 6, padding: '8px 12px', fontSize: 12, color: '#f43f5e', marginBottom: 14 }}>
                  <strong>Reasons:</strong> {Array.isArray(item.reasons) ? item.reasons.join(', ') : String(item.reasons)}
                </div>

                {/* Extracted Field Cards Grid */}
                <div style={{ marginBottom: 16 }}>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
                    {(() => {
                      const reasonsStr = (Array.isArray(item.reasons) ? item.reasons.join(' ') : String(item.reasons || '')).toLowerCase()
                      const qty = parseFloat(currentRecord.qty) || 0
                      const rate = parseFloat(currentRecord.rate) || 0
                      const gross = parseFloat(currentRecord.gross_amount) || 0
                      const discAmt = parseFloat(currentRecord.discount_amount) || 0
                      const taxable = parseFloat(currentRecord.taxable_amount) || 0
                      const cgstPct = parseFloat(currentRecord.cgst_pct) || 0
                      const cgst = parseFloat(currentRecord.cgst_amount) || 0
                      const sgstPct = parseFloat(currentRecord.sgst_pct) || 0
                      const sgst = parseFloat(currentRecord.sgst_amount) || 0
                      const finalVal = parseFloat(currentRecord.final_value || currentRecord.grand_total_final) || 0

                      return Object.entries(currentRecord).map(([key, val]) => {
                        const k = key.toLowerCase()
                        let isMismatched = false

                        if (k === 'gross_amount' && qty > 0 && rate > 0 && Math.abs((qty * rate) - gross) > 0.5) isMismatched = true
                        else if (k === 'taxable_amount' && gross > 0 && discAmt > 0 && Math.abs((gross - discAmt) - taxable) > 0.5) isMismatched = true
                        else if (k === 'cgst_amount' && taxable > 0 && cgstPct > 0 && Math.abs((taxable * (cgstPct / 100)) - cgst) > 0.5) isMismatched = true
                        else if (k === 'sgst_amount' && taxable > 0 && sgstPct > 0 && Math.abs((taxable * (sgstPct / 100)) - sgst) > 0.5) isMismatched = true
                        else if ((k === 'final_value' || k === 'grand_total_final') && (taxable > 0 || gross > 0) && Math.abs(((taxable > 0 ? taxable : gross) + cgst + sgst) - finalVal) > 0.5) isMismatched = true
                        else if (reasonsStr.includes(k)) isMismatched = true

                        return (
                          <div
                            key={key}
                            style={{
                              background: isMismatched ? 'rgba(244, 63, 94, 0.16)' : 'rgba(255,255,255,0.03)',
                              border: isMismatched ? '1px solid rgba(244, 63, 94, 0.65)' : '1px solid var(--border)',
                              borderRadius: 6,
                              padding: '8px 10px',
                              boxShadow: isMismatched ? '0 0 10px rgba(244, 63, 94, 0.15)' : undefined
                            }}
                          >
                            <label style={{ display: 'block', fontSize: 10, fontWeight: 700, color: isMismatched ? '#f43f5e' : '#aaa', textTransform: 'uppercase', marginBottom: 4 }}>
                              {key.replace(/_/g, ' ')}
                            </label>
                            {isEditing ? (
                              <input
                                type="text"
                                className="input"
                                value={String(val || '')}
                                onChange={(e) => handleFieldChange(key, e.target.value)}
                                style={{ width: '100%', fontSize: 12, borderColor: isMismatched ? '#f43f5e' : undefined, fontWeight: isMismatched ? 700 : 400 }}
                              />
                            ) : (
                              <div style={{ fontSize: 13, color: isMismatched ? '#ff6b81' : '#fff', fontFamily: 'monospace', fontWeight: isMismatched ? 700 : 400 }}>
                                {String(val)}
                              </div>
                            )}
                          </div>
                        )
                      })
                    })()}
                  </div>
                </div>

                {/* Approve / Dismiss Action Buttons */}
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 10, borderTop: '1px solid var(--border)' }}>
                  {!isEditing ? (
                    <>
                      <button className="btn btn-secondary btn-sm" onClick={() => handleStartEdit(item)}>
                        <Edit3 size={12} /> Edit Fields
                      </button>
                      <button className="btn btn-primary btn-sm" onClick={() => handleApproveWithEdits(item.id)}>
                        <CheckCircle size={12} /> Approve & Store
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={() => handleDismiss(item.id)} style={{ color: 'var(--red)' }}>
                        <XCircle size={12} /> Dismiss
                      </button>
                    </>
                  ) : (
                    <>
                      <button className="btn btn-secondary btn-sm" onClick={() => setEditingItemId(null)}>
                        <X size={12} /> Cancel Edit
                      </button>
                      <button className="btn btn-primary btn-sm" onClick={() => handleApproveWithEdits(item.id)}>
                        <Save size={12} /> Save Edits & Approve
                      </button>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
