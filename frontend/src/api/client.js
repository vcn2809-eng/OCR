import quotationApi from './quotationClient.js'

const EXPRESS_BASE = '/api'


// Export API implementation pointing to Express server on Port 5001
export const api = {
  getStats: async () => {
    try {
      const res = await fetch(`${EXPRESS_BASE}/stats`)
      if (!res.ok) throw new Error('Failed to fetch stats')
      return res.json()
    } catch (e) {
      console.error(e)
      return { total_documents: 0, total_value_extracted: 0, extracted_invoices: 0, quarantined_count: 0, by_type: {}, recent_documents: [] }
    }
  },
  uploadDocument: quotationApi.uploadQuotation,
  listDocuments: async (params = {}) => {
    const q = new URLSearchParams()
    if (params.page) q.append('page', params.page)
    if (params.limit || params.page_size) q.append('limit', params.limit || params.page_size)
    if (params.search || params.filename) q.append('search', params.search || params.filename)
    if (params.status && params.status !== 'all') q.append('status', params.status)
    if (params.document_type && params.document_type !== 'all') q.append('document_type', params.document_type)
    if (params.vendor_id && params.vendor_id !== 'all') q.append('vendor_id', params.vendor_id)

    const res = await fetch(`${EXPRESS_BASE}/quotations?${q.toString()}`)
    if (!res.ok) throw new Error('Failed to fetch documents')
    const data = await res.json()

    return {
      items: (data.items || []).map(d => ({
        document_id: d.id,
        id: d.id,
        original_filename: d.quotation_no ? `Doc ${d.quotation_no}` : `Doc #${d.id}`,
        file_type: 'pdf',
        document_type: d.document_type,
        status: d.extraction_status,
        uploaded_at: d.quotation_date,
      })),
      total: data.total || 0,
    }
  },
  getDocument: quotationApi.getQuotation,
  getDocumentRows: async (id) => {
    const res = await quotationApi.getLineItems(id)
    const items = res.items || []
    return items.map(item => {
      const { id: rowId, document_id, needs_review, review_reason, tax_breakdown, status_eta, ...rest } = item
      return rest
    })
  },
  linkVendorToDocument: () => Promise.resolve({ success: true }),
  reprocessDocument: () => Promise.resolve({ success: true }),
  deleteDocument: () => Promise.resolve({ success: true }),
  
  listVendors: async () => {
    const res = await fetch(`${EXPRESS_BASE}/vendors`)
    if (!res.ok) throw new Error('Failed to fetch vendors')
    return res.json()
  },
  getVendorById: async (id) => {
    const res = await fetch(`${EXPRESS_BASE}/vendors/${id}`)
    if (!res.ok) throw new Error('Failed to fetch vendor details')
    return res.json()
  },
  saveVendor: async (vendorName, address = '') => {
    const res = await fetch(`${EXPRESS_BASE}/vendors`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vendor_name: vendorName, address }),
    })
    if (!res.ok) throw new Error('Failed to save vendor')
    return res.json()
  },

  listQuarantine: async () => {
    const queue = await quotationApi.getReviewQueue()
    return {
      items: queue.map(q => ({
        id: q.id,
        document_id: q.document_id,
        document_type: 'Line Item Arithmetic Check',
        reasons: q.review_reason || 'Needs Review',
        record: q,
        flagged_at: new Date().toISOString(),
      })),
      total: queue.length
    }
  },
  resolveQuarantine: async (id, action, record) => {
    if (action === 'accept' && record) {
      await quotationApi.updateLineItem(id, record)
    }
    return { success: true }
  },
  bulkDismissQuarantine: () => Promise.resolve({ success: true }),
}

export default api
