import React, { useState, useEffect, useCallback } from 'react'
import { Cpu, Plus, RefreshCw, Sparkles } from 'lucide-react'
import api from '../api.js'
import { useToast } from '../ToastContext.jsx'

export default function LearningAgent() {
  const [aliases, setAliases] = useState([])
  const [loading, setLoading] = useState(true)
  const [newAlias, setNewAlias] = useState('')
  const [canonicalName, setCanonicalName] = useState('')
  const [category, setCategory] = useState('header')
  const [submitting, setSubmitting] = useState(false)
  const toast = useToast()

  const loadAliases = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.listAliases()
      setAliases(res.items || [])
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { loadAliases() }, [loadAliases])

  const handleLearn = async (e) => {
    e.preventDefault()
    if (!newAlias.trim() || !canonicalName.trim()) return
    setSubmitting(true)
    try {
      await api.learnAlias(newAlias.trim(), canonicalName.trim(), category)
      toast(`Learned alias "${newAlias}" -> "${canonicalName}"`, 'success')
      setNewAlias('')
      setCanonicalName('')
      loadAliases()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>Learning Agent</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
            Corrective feedback loop & dynamic schema alias learner
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={loadAliases}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Teach New Alias Form */}
      <div className="card" style={{ border: '1px solid rgba(168,85,247,0.3)', background: 'rgba(168,85,247,0.04)' }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 12px 0', color: 'var(--purple)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Sparkles size={16} /> Teach New Schema Mapping / Abbreviation Alias
        </h3>
        <form onSubmit={handleLearn} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 140px auto', gap: 12, alignItems: 'end' }}>
          <div>
            <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Raw Alias / Abbreviation</label>
            <input className="input" placeholder="e.g. mtrl / inv_no" value={newAlias} onChange={e => setNewAlias(e.target.value)} required style={{ width: '100%' }} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Canonical Field Name</label>
            <input className="input" placeholder="e.g. materials / invoice_number" value={canonicalName} onChange={e => setCanonicalName(e.target.value)} required style={{ width: '100%' }} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Category</label>
            <select className="select" value={category} onChange={e => setCategory(e.target.value)} style={{ width: '100%' }}>
              <option value="header">Header</option>
              <option value="item">Line Item</option>
              <option value="summary">Summary</option>
            </select>
          </div>
          <button type="submit" className="btn btn-primary" disabled={submitting} style={{ background: 'var(--purple)', color: '#fff' }}>
            <Plus size={14} /> {submitting ? 'Learning...' : 'Teach Alias'}
          </button>
        </form>
      </div>

      {/* Learned Aliases Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 48, textAlign: 'center' }}><div className="spinner" style={{ margin: 'auto' }} /></div>
        ) : aliases.length === 0 ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>No learned aliases stored yet</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: 'rgba(168,85,247,0.08)', borderBottom: '1px solid var(--border)', textAlign: 'left' }}>
                <th style={{ padding: '12px 16px', color: 'var(--purple)' }}>Raw Alias</th>
                <th style={{ padding: '12px 16px' }}>Canonical Field Name</th>
                <th style={{ padding: '12px 16px' }}>Category</th>
                <th style={{ padding: '12px 16px' }}>Confidence</th>
                <th style={{ padding: '12px 16px' }}>Occurrences</th>
              </tr>
            </thead>
            <tbody>
              {aliases.map((item, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid var(--border)', background: idx % 2 === 0 ? 'rgba(255,255,255,0.01)' : 'transparent' }}>
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontWeight: 600, color: 'var(--cyan)' }}>{item.alias}</td>
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontWeight: 700, color: 'var(--purple)' }}>{item.canonical_name}</td>
                  <td style={{ padding: '12px 16px', textTransform: 'capitalize' }}>{item.category}</td>
                  <td style={{ padding: '12px 16px', color: 'var(--green)' }}>{(item.confidence * 100).toFixed(0)}%</td>
                  <td style={{ padding: '12px 16px', color: 'var(--text-muted)' }}>{item.occurrence_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
