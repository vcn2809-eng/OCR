import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, CheckCircle, ArrowRight, Save, ShieldAlert, Search } from 'lucide-react'
import quotationApi from '../api/quotationClient.js'
import { formatIndianCurrency } from './QuotationsList.jsx'
import { useToast } from '../ToastContext.jsx'
import GhostSearchInput from '../components/GhostSearchInput.jsx'

export default function ReviewQueue() {
  const [flaggedItems, setFlaggedItems] = useState([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const toast = useToast()

  // Form edit state for selected item
  const [formData, setFormData] = useState({
    qty: '',
    rate: '',
    gross_amount: '',
    discount_pct: '',
    discount_amount: '',
    taxable_amount: '',
    cgst_pct: '',
    cgst_amount: '',
    sgst_pct: '',
    sgst_amount: '',
    final_value: '',
  })

  const loadQueue = async () => {
    setLoading(true)
    try {
      const res = await quotationApi.getReviewQueue()
      setFlaggedItems(res)
      if (res.length > 0) {
        setSelectedIndex(0)
        populateForm(res[0])
      }
    } catch (err) {
      console.error(err)
      toast('Failed to load review queue', 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadQueue()
  }, [])

  const populateForm = (item) => {
    if (!item) return
    setFormData({
      qty: String(item.qty || ''),
      rate: String(item.rate || ''),
      gross_amount: String(item.gross_amount || ''),
      discount_pct: String(item.discount_pct || ''),
      discount_amount: String(item.discount_amount || ''),
      taxable_amount: String(item.taxable_amount || ''),
      cgst_pct: String(item.cgst_pct || ''),
      cgst_amount: String(item.cgst_amount || ''),
      sgst_pct: String(item.sgst_pct || ''),
      sgst_amount: String(item.sgst_amount || ''),
      final_value: String(item.final_value || ''),
    })
  }

  const filteredQueue = flaggedItems.filter(item => {
    if (!searchQuery || !searchQuery.trim()) return true
    const q = searchQuery.toLowerCase().trim()
    const qNoMatch = String(item.quotation_no || item.document_no || '').toLowerCase().includes(q)
    const itemCodeMatch = String(item.item_code || '').toLowerCase().includes(q)
    const descMatch = String(item.description || '').toLowerCase().includes(q)
    const vendorMatch = String(item.vendor_name || '').toLowerCase().includes(q)
    const customerMatch = String(item.customer_name || '').toLowerCase().includes(q)
    const reasonMatch = String(item.review_reason || '').toLowerCase().includes(q)
    return qNoMatch || itemCodeMatch || descMatch || vendorMatch || customerMatch || reasonMatch
  })

  const handleItemSelect = (index) => {
    setSelectedIndex(index)
    populateForm(filteredQueue[index])
  }

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
  }

  const handleFormSubmit = async (e) => {
    e.preventDefault()
    if (filteredQueue.length === 0) return

    const currentItem = filteredQueue[selectedIndex]
    try {
      await quotationApi.updateLineItem(currentItem.id, formData)
      toast('Item corrected and re-validated successfully!', 'success')

      const updatedQueue = flaggedItems.filter(item => item.id !== currentItem.id)
      setFlaggedItems(updatedQueue)

      if (updatedQueue.length > 0) {
        const nextIndex = selectedIndex >= updatedQueue.length ? 0 : selectedIndex
        setSelectedIndex(nextIndex)
        populateForm(updatedQueue[nextIndex])
      } else {
        setSelectedIndex(0)
      }
    } catch (err) {
      toast(`Failed to update item: ${err.message}`, 'error')
    }
  }

  const handleSkipNext = () => {
    if (filteredQueue.length === 0) return
    const nextIndex = (selectedIndex + 1) % filteredQueue.length
    handleItemSelect(nextIndex)
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <div className="spinner" style={{ display: 'inline-block' }}></div>
        <div style={{ marginTop: 16, color: 'var(--text-secondary)' }}>Loading review queue...</div>
      </div>
    )
  }

  const selectedItem = filteredQueue[selectedIndex]

  return (
    <div>
      <div className="mb-4">
        <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>Discrepancy Review Queue</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
          Audit and resolve all line item math discrepancies across documents
        </p>
      </div>

      {flaggedItems.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '60px 40px' }}>
          <CheckCircle size={48} style={{ color: 'var(--green)', marginBottom: 16 }} />
          <h3 style={{ fontSize: 18, fontWeight: 700 }}>Review Queue Clear!</h3>
          <p style={{ color: 'var(--text-secondary)', marginTop: 8, maxWidth: 460, margin: '8px auto 0 auto' }}>
            No line items currently fail validation checks. All quotation math reconciles.
          </p>
          <Link to="/quotations" className="btn btn-primary mt-4">
            Browse Quotations
          </Link>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          
          {/* Flagged items left sidebar */}
          <div style={{ flex: '1', minWidth: '320px' }}>
            <div className="card" style={{ padding: '16px 20px', marginBottom: 12, background: 'rgba(251, 191, 36, 0.02)', border: '1px solid rgba(251, 191, 36, 0.15)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--amber)', fontWeight: 700, fontSize: 14 }}>
                <ShieldAlert size={18} />
                <span>{filteredQueue.length} Discrepancy Item(s) Flagged</span>
              </div>
            </div>

            {/* Search Bar inside sidebar */}
            <div style={{ marginBottom: 12 }}>
              <GhostSearchInput
                value={searchQuery}
                onChange={(val) => {
                  setSearchQuery(val)
                  setSelectedIndex(0)
                  populateForm(flaggedItems[0])
                }}
                placeholder="Search queue by Quote #, CPT code, vendor..."
              />
            </div>

            {filteredQueue.length === 0 ? (
              <div className="card" style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
                No flagged items matching "{searchQuery}"
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 'calc(100vh - 260px)', overflowY: 'auto' }}>
                {filteredQueue.map((item, idx) => {
                  const isSelected = idx === selectedIndex
                  return (
                    <div
                      key={item.id}
                      className="card"
                      style={{
                        cursor: 'pointer',
                        padding: '16px',
                        marginBottom: 0,
                        borderColor: isSelected ? 'var(--cyan)' : 'var(--border)',
                        background: isSelected ? 'rgba(0, 212, 255, 0.03)' : 'var(--bg-card)',
                        transition: 'all 0.15s ease',
                        borderLeft: '4px solid var(--amber)',
                      }}
                      onClick={() => handleItemSelect(idx)}
                    >
                      <div className="flex justify-between items-center mb-2">
                        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)' }}>
                          QUOTE NO: {item.quotation_no || item.document_no || `Doc #${item.document_id}`}
                        </span>
                        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                          Line #{item.line_no}
                        </span>
                      </div>
                      
                      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4, color: '#fff' }}>
                        {item.description}
                      </div>

                      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
                        Item Code: <strong style={{ color: 'var(--cyan)' }}>{item.item_code || 'N/A'}</strong>
                      </div>

                      <div className="flagged-reason-box">
                        ⚠ {item.review_reason || 'Math discrepancy in line totals'}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Detailed Resolution Form on Right */}
          <div style={{ flex: '1.6', minWidth: '420px' }}>
            {selectedItem ? (
              <form onSubmit={handleFormSubmit} className="card" style={{ padding: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 16 }}>
                  <div>
                    <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: '#fff' }}>
                      Audit Line Item #{selectedItem.line_no}: {selectedItem.item_code}
                    </h3>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                      Document: <strong>{selectedItem.quotation_no || selectedItem.document_no}</strong> • Vendor: <strong>{selectedItem.vendor_name || 'N/A'}</strong>
                    </div>
                  </div>
                  <span className="badge badge-needs_review">
                    <span className="badge-dot" /> Action Required
                  </span>
                </div>

                <div style={{ background: 'rgba(251, 191, 36, 0.06)', border: '1px solid rgba(251, 191, 36, 0.25)', borderRadius: 8, padding: '12px 16px', marginBottom: 20 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--amber)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <AlertTriangle size={15} /> Discrepancy Reason
                  </div>
                  <div style={{ fontSize: 13, color: '#fff', marginTop: 4 }}>
                    {selectedItem.review_reason || 'Extracted item values fail mathematical cross-validation.'}
                  </div>
                </div>

                {(() => {
                  const qty = parseFloat(formData.qty) || 0
                  const rate = parseFloat(formData.rate) || 0
                  const gross = parseFloat(formData.gross_amount) || 0
                  const discAmt = parseFloat(formData.discount_amount) || 0
                  const taxable = parseFloat(formData.taxable_amount) || 0
                  const cgstPct = parseFloat(formData.cgst_pct) || 0
                  const cgst = parseFloat(formData.cgst_amount) || 0
                  const sgstPct = parseFloat(formData.sgst_pct) || 0
                  const sgst = parseFloat(formData.sgst_amount) || 0
                  const finalVal = parseFloat(formData.final_value) || 0

                  const isGrossMismatched = qty > 0 && rate > 0 && Math.abs((qty * rate) - gross) > 0.5
                  const isTaxableMismatched = gross > 0 && discAmt > 0 && Math.abs((gross - discAmt) - taxable) > 0.5
                  const isCgstMismatched = taxable > 0 && cgstPct > 0 && Math.abs((taxable * (cgstPct / 100)) - cgst) > 0.5
                  const isSgstMismatched = taxable > 0 && sgstPct > 0 && Math.abs((taxable * (sgstPct / 100)) - sgst) > 0.5
                  const isFinalMismatched = (taxable > 0 || gross > 0) && Math.abs(((taxable > 0 ? taxable : gross) + cgst + sgst) - finalVal) > 0.5

                  return (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                      <div>
                        <label className="form-label">Quantity</label>
                        <input
                          type="text"
                          className="input"
                          name="qty"
                          value={formData.qty}
                          onChange={handleInputChange}
                        />
                      </div>
                      <div>
                        <label className="form-label">Rate / Unit Price</label>
                        <input
                          type="text"
                          className="input"
                          name="rate"
                          value={formData.rate}
                          onChange={handleInputChange}
                        />
                      </div>
                      <div>
                        <label className="form-label" style={{ color: isGrossMismatched ? '#f43f5e' : undefined, fontWeight: isGrossMismatched ? 700 : 400 }}>Gross Amount</label>
                        <input
                          type="text"
                          className="input"
                          name="gross_amount"
                          value={formData.gross_amount}
                          onChange={handleInputChange}
                          style={isGrossMismatched ? { borderColor: '#f43f5e', background: 'rgba(244, 63, 94, 0.16)', color: '#ff6b81', fontWeight: 700 } : undefined}
                        />
                      </div>
                      <div>
                        <label className="form-label">Discount %</label>
                        <input
                          type="text"
                          className="input"
                          name="discount_pct"
                          value={formData.discount_pct}
                          onChange={handleInputChange}
                        />
                      </div>
                      <div>
                        <label className="form-label" style={{ color: isTaxableMismatched ? '#f43f5e' : undefined, fontWeight: isTaxableMismatched ? 700 : 400 }}>Taxable Amount</label>
                        <input
                          type="text"
                          className="input"
                          name="taxable_amount"
                          value={formData.taxable_amount}
                          onChange={handleInputChange}
                          style={isTaxableMismatched ? { borderColor: '#f43f5e', background: 'rgba(244, 63, 94, 0.16)', color: '#ff6b81', fontWeight: 700 } : undefined}
                        />
                      </div>
                      <div>
                        <label className="form-label" style={{ color: isCgstMismatched ? '#f43f5e' : undefined, fontWeight: isCgstMismatched ? 700 : 400 }}>CGST Amount</label>
                        <input
                          type="text"
                          className="input"
                          name="cgst_amount"
                          value={formData.cgst_amount}
                          onChange={handleInputChange}
                          style={isCgstMismatched ? { borderColor: '#f43f5e', background: 'rgba(244, 63, 94, 0.16)', color: '#ff6b81', fontWeight: 700 } : undefined}
                        />
                      </div>
                      <div>
                        <label className="form-label" style={{ color: isSgstMismatched ? '#f43f5e' : undefined, fontWeight: isSgstMismatched ? 700 : 400 }}>SGST Amount</label>
                        <input
                          type="text"
                          className="input"
                          name="sgst_amount"
                          value={formData.sgst_amount}
                          onChange={handleInputChange}
                          style={isSgstMismatched ? { borderColor: '#f43f5e', background: 'rgba(244, 63, 94, 0.16)', color: '#ff6b81', fontWeight: 700 } : undefined}
                        />
                      </div>
                      <div>
                        <label className="form-label" style={{ color: isFinalMismatched ? '#f43f5e' : 'var(--cyan)', fontWeight: 700 }}>Final Net Value</label>
                        <input
                          type="text"
                          className="input"
                          name="final_value"
                          value={formData.final_value}
                          onChange={handleInputChange}
                          style={{
                            borderColor: isFinalMismatched ? '#f43f5e' : 'var(--cyan)',
                            background: isFinalMismatched ? 'rgba(244, 63, 94, 0.16)' : undefined,
                            color: isFinalMismatched ? '#ff6b81' : '#fff',
                            fontWeight: 700
                          }}
                        />
                      </div>
                    </div>
                  )
                })()}

                <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                  <button type="button" className="btn btn-secondary" onClick={handleSkipNext}>
                    Skip / Next <ArrowRight size={14} />
                  </button>
                  <button type="submit" className="btn btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <Save size={15} /> Save & Validate Line Item
                  </button>
                </div>
              </form>
            ) : (
              <div className="card" style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)' }}>
                Select an item from the queue list on the left to begin resolution.
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  )
}
