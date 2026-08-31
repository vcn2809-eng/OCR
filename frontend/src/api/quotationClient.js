const EXPRESS_API_BASE = 'http://localhost:5001/api'

async function request(endpoint, options = {}) {
  const url = `${EXPRESS_API_BASE}${endpoint}`
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  }

  if (options.body instanceof FormData) {
    delete config.headers['Content-Type']
  }

  const res = await fetch(url, config)
  if (!res.ok) {
    let msg = `HTTP ${res.status}: ${res.statusText}`
    try {
      const errData = await res.json()
      if (errData && errData.error) {
        msg = errData.error
      } else if (errData && errData.detail) {
        msg = errData.detail
      }
    } catch (e) {
      // ignore
    }
    throw new Error(msg)
  }
  return res.json()
}

export const quotationApi = {
  listQuotations: (params = {}) => {
    const q = new URLSearchParams()
    if (params.page) q.append('page', params.page)
    if (params.limit) q.append('limit', params.limit)
    if (params.search) q.append('search', params.search)
    if (params.status) q.append('status', params.status)
    if (params.document_type) q.append('document_type', params.document_type)
    return request(`/quotations?${q.toString()}`)
  },
  getQuotation: (id) => request(`/quotations/${id}`),
  getLineItems: (id, params = {}) => {
    const q = new URLSearchParams()
    if (params.page) q.append('page', params.page)
    if (params.limit) q.append('limit', params.limit)
    return request(`/quotations/${id}/line-items?${q.toString()}`)
  },
  getReviewQueue: () => request('/review-queue'),
  uploadQuotation: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request('/upload', {
      method: 'POST',
      body: formData,
    })
  },
  ingestTextData: (raw_text) => request('/quotations/ingest-text', {
    method: 'POST',
    body: JSON.stringify({ raw_text }),
  }),
  updateLineItem: (id, fields) => request(`/line-items/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(fields),
  }),
  searchDocuments: (params = {}) => {
    const q = new URLSearchParams()
    if (params.q) q.append('q', params.q)
    if (params.vendor_id) q.append('vendor_id', params.vendor_id)
    if (params.document_type) q.append('document_type', params.document_type)
    if (params.status) q.append('status', params.status)
    if (params.start_date) q.append('start_date', params.start_date)
    if (params.end_date) q.append('end_date', params.end_date)
    return request(`/search?${q.toString()}`)
  },

  searchLineItems: (query) => {
    const q = new URLSearchParams({ q: query })
    return request(`/search/line-items?${q.toString()}`)
  },
  submitSearchFeedback: (alias, canonical) => request('/search/feedback', {
    method: 'POST',
    body: JSON.stringify({ alias, canonical, accepted: true }),
  }),
  getGhostSuggestion: (q, options = {}) => {
    const params = new URLSearchParams({ q })
    return request(`/ghost-suggest?${params.toString()}`, options)
  },
  deleteQuotation: (id) => request(`/quotations/${id}`, { method: 'DELETE' }),
  batchDeleteQuotations: (ids) => request('/quotations/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  }),
}

export default quotationApi
