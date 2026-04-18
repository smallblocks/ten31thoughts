import React, { useState, useEffect } from 'react'

function SignalCard({ signal, onDismiss, onPromote }) {
  return (
    <div className="border border-border rounded-lg p-4 bg-surface">
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          {signal.item_title && (
            <a href={signal.item_url} target="_blank" rel="noopener noreferrer"
              className="text-xs text-text-secondary hover:text-brand-accent transition-colors block mb-1">
              {signal.item_title}
            </a>
          )}
          <h4 className="text-sm font-medium text-text-primary mb-2">{signal.topic_summary}</h4>
          <p className="text-sm text-text-primary leading-relaxed mb-3">{signal.why_it_matters}</p>
        </div>
      </div>
      
      {signal.excerpt && (
        <blockquote className="border-l-2 border-border pl-3 mb-3">
          <p className="text-xs text-text-secondary italic font-serif">{signal.excerpt}</p>
        </blockquote>
      )}
      
      <div className="flex items-center justify-end gap-2">
        <button 
          onClick={() => onPromote(signal.signal_id)}
          className="text-xs px-3 py-1 rounded bg-emerald-800 text-emerald-200 hover:bg-emerald-700 transition-colors"
        >
          → Note
        </button>
        <button 
          onClick={() => onDismiss(signal.signal_id)}
          className="text-xs px-3 py-1 rounded bg-gray-800 text-red-400 hover:bg-red-900/30 transition-colors"
        >
          ✕
        </button>
      </div>
    </div>
  )
}

export default function Signals() {
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadSignals()
  }, [])

  async function loadSignals() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/signals/?limit=100')
      if (!res.ok) throw new Error('Failed to load signals')
      setSignals(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function dismissSignal(id) {
    try {
      const res = await fetch(`/api/signals/${id}/dismiss`, { method: 'PATCH' })
      if (res.ok || res.status === 204) {
        setSignals(prev => prev.filter(s => s.signal_id !== id))
      }
    } catch (e) {
      console.error('Failed to dismiss signal:', e)
    }
  }

  async function promoteSignal(id) {
    try {
      const res = await fetch(`/api/signals/${id}/promote`, { method: 'POST' })
      if (res.ok) {
        setSignals(prev => prev.filter(s => s.signal_id !== id))
      }
    } catch (e) {
      console.error('Failed to promote signal:', e)
    }
  }

  if (loading) return <div className="p-6 text-text-secondary">Loading signals...</div>
  if (error) return <div className="p-6 text-red-400">Error: {error}</div>

  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-medium text-text-primary">Signals</h2>
          <p className="text-sm text-text-secondary">
            Noteworthy content that doesn't match existing notes ({signals.length})
          </p>
        </div>
      </div>

      {signals.length === 0 ? (
        <div className="text-center py-12">
          <h3 className="text-sm font-medium text-text-primary mb-2">No signals to triage</h3>
          <p className="text-sm text-text-secondary">
            Signals appear when new content doesn't match any existing notes but seems noteworthy.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {signals.map(s => (
            <SignalCard
              key={s.signal_id}
              signal={s}
              onDismiss={dismissSignal}
              onPromote={promoteSignal}
            />
          ))}
        </div>
      )}
    </div>
  )
}