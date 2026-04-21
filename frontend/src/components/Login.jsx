import React, { useState, useRef, useEffect } from 'react'

export default function Login({ onLogin }) {
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const pinRef = useRef(null)

  useEffect(() => {
    pinRef.current?.focus()
  }, [])

  const handleLogin = async () => {
    if (!pin.trim()) return
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ pin: pin.trim() }),
      })
      if (res.ok) {
        onLogin()
      } else {
        const err = await res.json().catch(() => ({}))
        setError(err.detail || 'Invalid PIN')
      }
    } catch (e) {
      setError('Connection failed')
    }
    setSubmitting(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: '#0a0a0c' }}>
      <div className="w-full max-w-xs">
        <div className="text-center mb-10">
          <h1 className="font-mono text-2xl tracking-widest text-text-primary font-bold">
            TEN31
          </h1>
          <p className="font-mono text-xs tracking-wider mt-2" style={{ color: '#e94560' }}>
            THOUGHTS
          </p>
        </div>

        <div className="mb-4">
          <input
            ref={pinRef}
            type="password"
            inputMode="numeric"
            pattern="[0-9]*"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleLogin() }}
            placeholder="Enter PIN"
            className="w-full px-4 py-3 rounded-lg font-mono text-lg text-center tracking-widest outline-none"
            style={{
              background: '#16161a',
              border: `1px solid ${error ? '#8b3a3a' : '#2a2a30'}`,
              color: '#e8e8ea',
            }}
          />
        </div>

        {error && (
          <p className="font-mono text-xs text-center mb-3" style={{ color: '#c55' }}>
            {error}
          </p>
        )}

        <button
          onClick={handleLogin}
          disabled={submitting || !pin.trim()}
          className="w-full py-3 rounded-lg font-mono text-sm font-semibold tracking-wider transition-colors"
          style={{
            background: pin.trim() ? '#e94560' : '#16161a',
            border: pin.trim() ? 'none' : '1px solid #2a2a30',
            color: pin.trim() ? '#0a0a0c' : '#888892',
            cursor: pin.trim() ? 'pointer' : 'default',
          }}
        >
          {submitting ? 'Signing in…' : 'Sign In'}
        </button>

        <footer className="text-center mt-12">
          <p className="font-mono text-xs" style={{ color: '#2a2a30' }}>
            Macro Intelligence
          </p>
        </footer>
      </div>
    </div>
  )
}
