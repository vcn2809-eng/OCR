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

        if (res && res.suggestion && res.suggestion.trim()) {
          const sug = res.suggestion.trim()
          
          // Only show ghost completion if the suggestion is NOT identical to what user typed
          if (sug.toLowerCase() !== value.trim().toLowerCase()) {
            if (sug.toLowerCase().startsWith(value.toLowerCase())) {
              const remaining = sug.slice(value.length)
              if (remaining) {
                setSuggestion(sug)
                setGhostSuffix(`${remaining} (Tab ↹)`)
              } else {
                setSuggestion(null)
                setGhostSuffix('')
              }
            } else {
              setSuggestion(sug)
              setGhostSuffix(` → ${sug} (Tab ↹)`)
            }
          } else {
            setSuggestion(null)
            setGhostSuffix('')
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
    if ((e.key === 'Tab' || e.key === 'ArrowRight') && suggestion) {
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
          onClick={() => {
            if (suggestion) {
              onChange(suggestion)
              setSuggestion(null)
              setGhostSuffix('')
            }
          }}
          style={{
            position: 'absolute',
            left: 32,
            top: 0,
            bottom: 0,
            display: 'flex',
            alignItems: 'center',
            pointerEvents: 'auto',
            cursor: 'pointer',
            zIndex: 3,
            fontSize: 13,
            fontFamily: 'inherit',
            whiteSpace: 'pre',
            overflow: 'hidden',
            paddingRight: 12
          }}
        >
          <span style={{ visibility: 'hidden' }}>{value}</span>
          <span style={{ color: 'var(--cyan)', opacity: 0.85, fontWeight: 600 }}>
            {ghostSuffix}
          </span>
        </div>
      )}
    </div>
  )
}
