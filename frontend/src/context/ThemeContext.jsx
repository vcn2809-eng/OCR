import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'

const ThemeContext = createContext({
  theme: 'dark',
  toggleTheme: () => {}
})

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('nissigrid_theme') || 'dark'
  })
  const [showSecretIndicator, setShowSecretIndicator] = useState(false)
  const [indicatorText, setIndicatorText] = useState('')

  const applyTheme = useCallback((newTheme) => {
    document.documentElement.setAttribute('data-theme', newTheme)
    document.body.setAttribute('data-theme', newTheme)
    localStorage.setItem('nissigrid_theme', newTheme)
  }, [])

  useEffect(() => {
    applyTheme(theme)
  }, [theme, applyTheme])

  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const nextTheme = prev === 'dark' ? 'light' : 'dark'
      applyTheme(nextTheme)
      setIndicatorText(nextTheme === 'light' ? '☀️ Light Mode (Shift + D to toggle)' : '🌙 Dark Mode (Shift + D to toggle)')
      setShowSecretIndicator(true)
      setTimeout(() => setShowSecretIndicator(false), 2200)
      return nextTheme
    })
  }, [applyTheme])

  // Secret keyboard listeners: Shift + D, Alt + D, Alt + T, Cmd/Ctrl + Shift + D
  useEffect(() => {
    const handleKeyDown = (e) => {
      const isInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target?.tagName) || e.target?.isContentEditable
      
      // 1. Shift + D or Shift + T (when not typing in an input)
      if ((e.shiftKey && (e.key === 'D' || e.key === 'd' || e.key === 'T' || e.key === 't')) && !isInput) {
        e.preventDefault()
        toggleTheme()
        return
      }

      // 2. Alt + D or Alt + T or Ctrl/Cmd + Shift + D (always triggers even if focused)
      if ((e.altKey && (e.key === 'd' || e.key === 'D' || e.key === 't' || e.key === 'T')) ||
          ((e.metaKey || e.ctrlKey) && e.shiftKey && (e.key === 'd' || e.key === 'D'))) {
        e.preventDefault()
        toggleTheme()
        return
      }

      // 3. Simple key 'D' or 'T' when completely outside any form input
      if (!isInput && !e.ctrlKey && !e.metaKey && !e.altKey) {
        if (e.key === 'D' || e.key === 'd') {
          // Check if no active modal is typing
          toggleTheme()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [toggleTheme])

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
      {/* Sleek Secret Floating Theme HUD Indicator */}
      {showSecretIndicator && (
        <div
          style={{
            position: 'fixed',
            top: 24,
            left: '50%',
            transform: 'translateX(-50%)',
            background: theme === 'light' ? '#ffffff' : '#0f172a',
            color: theme === 'light' ? '#0f172a' : '#ffffff',
            padding: '10px 20px',
            borderRadius: 30,
            border: theme === 'light' ? '1px solid #cbd5e1' : '1px solid rgba(0, 212, 255, 0.4)',
            boxShadow: '0 12px 36px rgba(0, 0, 0, 0.3)',
            zIndex: 99999,
            fontSize: 13,
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            animation: 'fadeInOut 2.2s ease-in-out',
            pointerEvents: 'none',
            letterSpacing: '0.02em'
          }}
        >
          <span>{indicatorText}</span>
        </div>
      )}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}

export default ThemeContext
