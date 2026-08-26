import React from 'react'
import { Link } from 'react-router-dom'
import { Loader2, CheckCircle, ArrowRight, Layers } from 'lucide-react'
import { useIngestion } from '../context/IngestionContext.jsx'

export default function BackgroundIngestionStatus() {
  const { ingesting, filesQueue, currentIndex, batchCompleted, batchStats } = useIngestion()

  if (!ingesting && !batchCompleted) return null

  const currentFile = filesQueue[currentIndex]

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        zIndex: 9999,
        width: 340,
        background: ingesting ? 'rgba(15, 23, 42, 0.95)' : 'rgba(20, 83, 45, 0.95)',
        border: `1px solid ${ingesting ? 'rgba(0, 212, 255, 0.4)' : 'rgba(34, 197, 94, 0.4)'}`,
        boxShadow: '0 10px 30px rgba(0, 0, 0, 0.5)',
        backdropFilter: 'blur(10px)',
        borderRadius: 12,
        padding: '14px 16px',
        color: '#fff',
        animation: 'slideUp 0.3s ease-out'
      }}
    >
      {ingesting ? (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, color: 'var(--cyan)' }}>
              <Loader2 size={16} className="spinner" />
              <span>Background Extraction ({currentIndex + 1}/{filesQueue.length})</span>
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Running</span>
          </div>

          <div style={{ fontSize: 12, color: 'var(--text-secondary)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', marginBottom: 8 }}>
            {currentFile ? currentFile.name : 'Processing document...'}
          </div>

          <div style={{ height: 4, background: 'rgba(255, 255, 255, 0.1)', borderRadius: 2, overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${currentFile ? currentFile.progress : 50}%`,
                background: 'linear-gradient(90deg, var(--cyan), var(--purple))',
                transition: 'width 0.3s ease'
              }}
            />
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <CheckCircle size={18} style={{ color: 'var(--green)' }} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>Extraction Complete</div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.7)' }}>
                {batchStats.okCount + batchStats.reviewCount} file(s) ingested into PostgreSQL
              </div>
            </div>
          </div>
          <Link
            to="/documents"
            className="btn btn-secondary btn-sm"
            style={{ fontSize: 11, padding: '4px 8px', flexShrink: 0, gap: 4 }}
          >
            Explorer <ArrowRight size={12} />
          </Link>
        </div>
      )}
    </div>
  )
}
