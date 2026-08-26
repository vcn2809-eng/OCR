import React from 'react'

export default function StatusBadge({ status }) {
  const s = (status || 'queued').toLowerCase()

  let badgeClass = 'badge-processing'
  if (['stored', 'done', 'success'].includes(s)) {
    badgeClass = 'badge-done'
  } else if (['failed', 'error'].includes(s)) {
    badgeClass = 'badge-failed'
  }

  return (
    <span className={`badge ${badgeClass}`} style={{ padding: '2px 8px', fontSize: 11, textTransform: 'uppercase' }}>
      <span className="badge-dot" />
      {s}
    </span>
  )
}
