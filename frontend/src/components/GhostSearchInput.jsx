import React, { useState, useEffect, useRef } from 'react'
import { Search } from 'lucide-react'
import quotationApi from '../api/quotationClient.js'

export default function GhostSearchInput({
  value = '',
  onChange,
  onSubmit,
  placeholder = 'Search...',
  className = 'input',
  style = {}
}) {
  const [suggestion, setSuggestion] = useState(null)
  const [ghostSuffix, setGhostSuffix] = useState('')
  const abortControllerRef = useRef(null)

  useEffect(() => {
    if (!value || !value.trim()) {
      setSuggestion(null)
      setGhostSuffix('')
      return
    }

    // Cancel previous in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    abortControllerRef.current = new AbortController()

    const timer = setTimeout(async () => {
      try {
        const res = await quotationApi.getGhostSuggestion(value, {
          signal: abortControllerRef.current.signal
        })

        if (res && res.suggestion) {
          const sug = res.suggestion
          setSuggestion(sug)

          // Check if ghost completion is a direct prefix continuation
          if (sug.toLowerCase().startsWith(value.toLowerCase())) {
            setGhostSuffix(sug.slice(value.length) + ' (Tab ↹)')
          } else {
            // Case replacement or column completion (e.g. srl -> SRL)
            setGhostSuffix(` → ${sug} (Tab ↹)`)
          }
        } else {
          setSuggestion(null)
          setGhostSuffix('')
        }
      } catch (err) {
        if (err.name !== 'AbortError') {
          setSuggestion(null)
          setGhostSuffix('')
        }
      }
    }, 120) // 120ms debounce

    return () => {
      clearTimeout(timer)
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [value])

  const handleKeyDown = (e) => {
    if (e.key === 'Tab' && suggestion) {
      e.preventDefault()
      onChange(suggestion)
      setSuggestion(null)
      setGhostSuffix('')
    } else if (e.key === 'Escape') {
      setSuggestion(null)
      setGhostSuffix('')
    } else if (e.key === 'Enter' && onSubmit) {
      onSubmit(e)
    }
  }

  return (
    <div className="search-wrap" style={{ position: 'relative', width: '100%', ...style }}>
      <Search size={16} style={{ zIndex: 3, pointerEvents: 'none' }} />
      <input
        type="text"
        className={className}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        style={{
          position: 'relative',
          background: 'transparent',
          zIndex: 2,
          color: '#fff',
          width: '100%',
        }}
      />

      {/* Inline Ghost-Text Prediction Overlay */}
      {ghostSuffix && (
        <div
          style={{
            position: 'absolute',
            left: 32,
            top: 0,
            bottom: 0,
            display: 'flex',
            alignItems: 'center',
            pointerEvents: 'none',
            zIndex: 1,
            fontSize: 13,
            fontFamily: 'inherit',
            whiteSpace: 'pre',
            overflow: 'hidden',
            paddingRight: 12
          }}
        >
          <span style={{ visibility: 'hidden' }}>{value}</span>
          <span style={{ color: 'var(--cyan)', opacity: 0.65, fontWeight: 500 }}>
            {ghostSuffix}
          </span>
        </div>
      )}
    </div>
  )
}
