import React, { useState, useEffect } from 'react'

// Single API Base URL Constant at top of file
const API_BASE_URL = 'http://127.0.0.1:8000'

export default function VendorSelector() {
  const [vendors, setVendors] = useState([])
  const [selectedVendorId, setSelectedVendorId] = useState('')
  const [vendorDetail, setVendorDetail] = useState(null)

  // Explicit 3-State Handling
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [error, setError] = useState(null)

  // Add Vendor Form State
  const [showAddForm, setShowAddForm] = useState(false)
  const [newVendorName, setNewVendorName] = useState('')
  const [newVendorAddress, setNewVendorAddress] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Fetch Vendor List on Mount using plain fetch()
  const fetchVendors = async () => {
    setLoadingList(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE_URL}/vendors`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const data = await res.json()
      setVendors(data || [])
    } catch (err) {
      setError(`Failed to load vendors: ${err.message}`)
    } finally {
      setLoadingList(false)
    }
  }

  useEffect(() => {
    fetchVendors()
  }, [])

  // Fetch Selected Vendor Details using plain fetch()
  const handleVendorSelect = async (e) => {
    const vendorId = e.target.value
    setSelectedVendorId(vendorId)
    setVendorDetail(null)

    if (!vendorId) return

    setLoadingDetails(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE_URL}/vendors/${vendorId}`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const data = await res.json()
      setVendorDetail(data)
    } catch (err) {
      setError(`Failed to load vendor details: ${err.message}`)
    } finally {
      setLoadingDetails(false)
    }
  }

  // Create New Vendor Handler using plain fetch()
  const handleCreateVendor = async (e) => {
    e.preventDefault()
    if (!newVendorName.trim()) return

    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE_URL}/vendors`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vendor_name: newVendorName.trim(),
          address: newVendorAddress.trim(),
        }),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      const createdId = data.vendor_id

      setNewVendorName('')
      setNewVendorAddress('')
      setShowAddForm(false)

      // Refresh list and select new vendor
      await fetchVendors()
      setSelectedVendorId(createdId)
      
      // Load details for created vendor
      setLoadingDetails(true)
      const detailRes = await fetch(`${API_BASE_URL}/vendors/${createdId}`)
      if (detailRes.ok) {
        const detailData = await detailRes.json()
        setVendorDetail(detailData)
      }
    } catch (err) {
      setError(`Failed to save vendor: ${err.message}`)
    } finally {
      setSubmitting(false)
      setLoadingDetails(false)
    }
  }

  return (
    <div style={{
      background: 'rgba(255, 255, 255, 0.03)',
      border: '1px solid var(--border, rgba(255, 255, 255, 0.1))',
      borderRadius: 12,
      padding: 20,
      marginBottom: 24,
      boxShadow: '0 8px 32px rgba(0, 0, 0, 0.2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: 'var(--text-primary, #fff)', display: 'flex', alignItems: 'center', gap: 8 }}>
          🏢 Vendor Lookup & Selector
        </h3>
        <button
          className="btn btn-secondary btn-sm"
          style={{ padding: '6px 12px', fontSize: 12, borderRadius: 6 }}
          onClick={() => setShowAddForm(s => !s)}
        >
          {showAddForm ? '✕ Cancel' : '+ Add New Vendor'}
        </button>
      </div>

      {/* Explicit Error State */}
      {error && (
        <div style={{
          background: 'rgba(244, 63, 94, 0.1)',
          border: '1px solid rgba(244, 63, 94, 0.3)',
          borderRadius: 8,
          padding: '10px 14px',
          color: '#f43f5e',
          fontSize: 13,
          marginBottom: 14,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <span>⚠ {error}</span>
          <button
            onClick={fetchVendors}
            style={{
              background: 'transparent',
              border: '1px solid #f43f5e',
              color: '#f43f5e',
              padding: '2px 8px',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 11,
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Add Vendor Form Panel */}
      {showAddForm && (
        <form onSubmit={handleCreateVendor} style={{
          background: 'rgba(0, 212, 255, 0.04)',
          border: '1px solid rgba(0, 212, 255, 0.2)',
          borderRadius: 8,
          padding: 14,
          marginBottom: 16,
        }}>
          <h4 style={{ margin: '0 0 10px 0', fontSize: 13, color: '#00d4ff' }}>Create New Vendor</h4>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#aaa', marginBottom: 4 }}>Vendor Name *</label>
              <input
                type="text"
                className="input"
                placeholder="e.g. AIC Enterprises"
                value={newVendorName}
                onChange={e => setNewVendorName(e.target.value)}
                required
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#aaa', marginBottom: 4 }}>Address</label>
              <input
                type="text"
                className="input"
                placeholder="e.g. Peenya Industrial Estate, Bangalore"
                value={newVendorAddress}
                onChange={e => setNewVendorAddress(e.target.value)}
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </div>
          </div>
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={submitting || !newVendorName.trim()}
          >
            {submitting ? 'Saving...' : 'Save Vendor'}
          </button>
        </form>
      )}

      {/* Explicit Loading List State */}
      {loadingList ? (
        <div style={{ padding: '16px 0', color: '#888', fontSize: 13, display: 'flex', alignItems: 'center', gap: 10 }}>
          <div className="spinner" style={{ width: 16, height: 16 }} /> Loading vendor list...
        </div>
      ) : (
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#aaa', marginBottom: 6 }}>
            Select Vendor ({vendors.length} available)
          </label>
          <select
            value={selectedVendorId}
            onChange={handleVendorSelect}
            className="select"
            style={{
              width: '100%',
              padding: '10px 14px',
              fontSize: 14,
              borderRadius: 8,
              background: '#0e1626',
              color: '#fff',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              cursor: 'pointer',
            }}
          >
            <option value="">-- Choose a Vendor --</option>
            {vendors.map(v => (
              <option key={v.vendor_id} value={v.vendor_id}>
                {v.vendor_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Explicit Loading Selected Vendor Details State */}
      {loadingDetails && (
        <div style={{ marginTop: 16, padding: '14px', color: '#00d4ff', fontSize: 13, display: 'flex', alignItems: 'center', gap: 10 }}>
          <div className="spinner" style={{ width: 14, height: 14 }} /> Fetching vendor details...
        </div>
      )}

      {/* Vendor Details Panel */}
      {vendorDetail && !loadingDetails && (
        <div style={{
          marginTop: 16,
          background: 'rgba(0, 212, 255, 0.05)',
          border: '1px solid rgba(0, 212, 255, 0.25)',
          borderRadius: 8,
          padding: 16,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: '#00d4ff', letterSpacing: '0.05em' }}>
              SELECTED VENDOR DETAILS
            </span>
            <span style={{ fontSize: 10, fontFamily: 'monospace', color: '#777' }}>
              ID: {vendorDetail.vendor_id}
            </span>
          </div>

          <div style={{ fontSize: 16, fontWeight: 700, color: '#fff', marginBottom: 6 }}>
            {vendorDetail.vendor_name}
          </div>

          <div style={{ fontSize: 13, color: '#ccc', lineHeight: '1.5', whiteSpace: 'pre-wrap' }}>
            📍 <strong>Address:</strong> {vendorDetail.address || 'No address registered'}
          </div>

          {vendorDetail.created_at && (
            <div style={{ marginTop: 10, fontSize: 11, color: '#777', display: 'flex', gap: 16 }}>
              <span>Created: {new Date(vendorDetail.created_at).toLocaleString()}</span>
              {vendorDetail.updated_at && <span>Updated: {new Date(vendorDetail.updated_at).toLocaleString()}</span>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
