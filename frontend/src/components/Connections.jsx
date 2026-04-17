import React, { useState, useEffect } from 'react'

const RELATION_OPTIONS = [
  { value: '', label: 'All Relations' },
  { value: 'reinforces', label: 'Reinforces' },
  { value: 'extends', label: 'Extends' },
  { value: 'complicates', label: 'Complicates' },
  { value: 'contradicts', label: 'Contradicts' },
  { value: 'echoes_mechanism', label: 'Echoes Mechanism' },
]

const RELATION_COLORS = {
  reinforces: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  extends: 'bg-blue-900/40 text-blue-300 border-blue-800',
  complicates: 'bg-amber-900/40 text-amber-300 border-amber-800',
  contradicts: 'bg-red-900/40 text-red-300 border-red-800',
  echoes_mechanism: 'bg-purple-900/40 text-purple-300 border-purple-800',
}

function RelationBadge({ relation }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${RELATION_COLORS[relation] || 'bg-gray-800 text-gray-400 border-gray-700'}`}>
      {relation.replace(/_/g, ' ')}
    </span>
  )
}

function StrengthBar({ strength }) {
  if (strength == null) return null
  const pct = Math.round(strength * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-800 rounded-full">
        <div className="h-1.5 bg-brand-accent rounded-full" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 font-mono w-8 text-right">{pct}%</span>
    </div>
  )
}

function StarRating({ current, onRate }) {
  const [hover, setHover] = useState(0)
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map(star => (
        <button
          key={star}
          onMouseEnter={() => setHover(star)}
          onMouseLeave={() => setHover(0)}
          onClick={() => onRate(star)}
          className={`text-sm transition-colors ${
            star <= (hover || current || 0)
              ? 'text-amber-400'
              : 'text-gray-600 hover:text-gray-400'
          }`}
        >
          ★
        </button>
      ))}
    </div>
  )
}

function ConnectionCard({ conn, onRate, onDismiss, onPromote }) {
  const notePreview = conn.note_body
    ? (conn.note_body.length > 120 ? conn.note_body.slice(0, 120) + '…' : conn.note_body)
    : null

  return (
    <div className="border border-gray-800 rounded-lg p-4 bg-gray-900/20">
      {/* Source content */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            {conn.item_title ? (
              <a href={conn.item_url} target="_blank" rel="noopener noreferrer"
                className="text-sm font-medium text-white hover:text-brand-accent transition-colors">
                {conn.item_title}
              </a>
            ) : (
              <span className="text-sm text-gray-400">Unknown source</span>
            )}
            <RelationBadge relation={conn.relation} />
          </div>
          {notePreview && (
            <p className="text-xs text-gray-500 mb-2">
              → <span className="text-gray-400">{conn.note_title || 'Note'}</span>: {notePreview}
            </p>
          )}
        </div>
      </div>

      {/* Articulation */}
      <p className="text-xs text-gray-300 leading-relaxed mb-2">{conn.articulation}</p>

      {/* Excerpt */}
      {conn.excerpt && (
        <blockquote className="border-l-2 border-gray-700 pl-3 mb-2">
          <p className="text-xs text-gray-400 italic">{conn.excerpt}</p>
          {conn.excerpt_location && (
            <cite className="text-xs text-gray-600 not-italic">{conn.excerpt_location}</cite>
          )}
        </blockquote>
      )}

      {/* Principles invoked */}
      {conn.principles_invoked && conn.principles_invoked.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {conn.principles_invoked.map((p, i) => (
            <span key={i} className="text-[10px] bg-gray-800 text-gray-500 px-1.5 py-0.5 rounded">
              {typeof p === 'string' ? p : p.name || p.principle || JSON.stringify(p)}
            </span>
          ))}
        </div>
      )}

      {/* Strength bar */}
      <div className="mb-3">
        <StrengthBar strength={conn.strength} />
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <StarRating current={conn.user_rating} onRate={rating => onRate(conn.connection_id, rating)} />
        <div className="flex items-center gap-2">
          <button onClick={() => onPromote(conn.connection_id)}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-emerald-400 hover:bg-emerald-900/30 transition-colors"
            title="Promote to Note">
            → Note
          </button>
          <button onClick={() => onDismiss(conn.connection_id)}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-red-400 hover:bg-red-900/30 transition-colors"
            title="Dismiss">
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}

function SignalCard({ signal, onDismiss, onPromote }) {
  return (
    <div className="border border-gray-800 rounded-lg p-4 bg-gray-900/20">
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          {signal.item_title && (
            <a href={signal.item_url} target="_blank" rel="noopener noreferrer"
              className="text-xs text-gray-500 hover:text-brand-accent transition-colors">
              {signal.item_title}
            </a>
          )}
          <h4 className="text-sm font-medium text-white mt-1">{signal.topic_summary}</h4>
        </div>
      </div>
      <p className="text-xs text-gray-300 leading-relaxed mb-3">{signal.why_it_matters}</p>
      {signal.excerpt && (
        <blockquote className="border-l-2 border-gray-700 pl-3 mb-3">
          <p className="text-xs text-gray-400 italic">{signal.excerpt}</p>
        </blockquote>
      )}
      <div className="flex items-center justify-end gap-2">
        <button onClick={() => onPromote(signal.signal_id)}
          className="text-xs px-2 py-1 rounded bg-gray-800 text-emerald-400 hover:bg-emerald-900/30 transition-colors">
          → Note
        </button>
        <button onClick={() => onDismiss(signal.signal_id)}
          className="text-xs px-2 py-1 rounded bg-gray-800 text-red-400 hover:bg-red-900/30 transition-colors">
          ✕
        </button>
      </div>
    </div>
  )
}

export default function Connections() {
  const [connections, setConnections] = useState([])
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [subTab, setSubTab] = useState('connections')

  // Filters
  const [filterRelation, setFilterRelation] = useState('')
  const [minStrength, setMinStrength] = useState(0)
  const [showDismissed, setShowDismissed] = useState(false)
  const [showRated, setShowRated] = useState(false)

  useEffect(() => { loadConnections() }, [filterRelation, minStrength, showDismissed, showRated])
  useEffect(() => { if (subTab === 'signals') loadSignals() }, [subTab])

  async function loadConnections() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (filterRelation) params.set('relation', filterRelation)
      if (minStrength > 0) params.set('min_strength', minStrength)
      if (!showRated) params.set('unrated', 'true')
      if (showDismissed) params.set('dismissed', 'true')
      params.set('limit', '50')

      const res = await fetch(`/api/connections/?${params}`)
      if (!res.ok) throw new Error('Failed to load connections')
      setConnections(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadSignals() {
    try {
      const res = await fetch('/api/signals/?limit=50')
      if (res.ok) setSignals(await res.json())
    } catch (e) {
      console.error('Failed to load signals:', e)
    }
  }

  async function rateConnection(id, rating) {
    const res = await fetch(`/api/connections/${id}/rating`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    })
    if (res.ok) {
      setConnections(prev =>
        prev.map(c => c.connection_id === id ? { ...c, user_rating: rating } : c)
      )
    }
  }

  async function dismissConnection(id) {
    const res = await fetch(`/api/connections/${id}`, { method: 'DELETE' })
    if (res.ok || res.status === 204) {
      setConnections(prev => prev.filter(c => c.connection_id !== id))
    }
  }

  async function promoteConnection(id) {
    const res = await fetch(`/api/connections/${id}/promote`, { method: 'POST' })
    if (res.ok) {
      setConnections(prev =>
        prev.map(c => c.connection_id === id ? { ...c, user_promoted_to_note: true } : c)
      )
    }
  }

  async function dismissSignal(id) {
    const res = await fetch(`/api/signals/${id}/dismiss`, { method: 'PATCH' })
    if (res.ok || res.status === 204) {
      setSignals(prev => prev.filter(s => s.signal_id !== id))
    }
  }

  async function promoteSignal(id) {
    const res = await fetch(`/api/signals/${id}/promote`, { method: 'POST' })
    if (res.ok) {
      setSignals(prev => prev.filter(s => s.signal_id !== id))
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-medium text-white">Connections</h2>
          <p className="text-sm text-gray-500">Review how new content relates to your notes</p>
        </div>
        {/* Sub-tab toggle */}
        <div className="flex gap-1 bg-gray-900 rounded-lg p-0.5 border border-gray-800">
          <button
            onClick={() => setSubTab('connections')}
            className={`text-sm px-3 py-1 rounded transition-colors ${
              subTab === 'connections' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Connections
          </button>
          <button
            onClick={() => setSubTab('signals')}
            className={`text-sm px-3 py-1 rounded transition-colors ${
              subTab === 'signals' ? 'bg-gray-800 text-white' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            Signals
          </button>
        </div>
      </div>

      {subTab === 'connections' && (
        <>
          {/* Filters */}
          <div className="flex flex-wrap gap-3 mb-4">
            <select
              value={filterRelation}
              onChange={e => setFilterRelation(e.target.value)}
              className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-brand-accent"
            >
              {RELATION_OPTIONS.map(r => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-500">Min strength:</label>
              <input
                type="range"
                min="0" max="1" step="0.05"
                value={minStrength}
                onChange={e => setMinStrength(parseFloat(e.target.value))}
                className="w-24"
              />
              <span className="text-xs text-gray-400 font-mono w-8">{Math.round(minStrength * 100)}%</span>
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={showDismissed}
                onChange={e => setShowDismissed(e.target.checked)}
                className="rounded bg-gray-800 border-gray-700"
              />
              Dismissed
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={showRated}
                onChange={e => setShowRated(e.target.checked)}
                className="rounded bg-gray-800 border-gray-700"
              />
              Show rated
            </label>
          </div>

          {loading ? (
            <div className="text-gray-400 text-sm">Loading connections...</div>
          ) : error ? (
            <div className="text-red-400 text-sm">Error: {error}</div>
          ) : connections.length === 0 ? (
            <div className="text-center py-12">
              <div className="w-16 h-16 rounded-xl bg-gray-800 flex items-center justify-center mx-auto mb-4">
                <span className="text-3xl">🔗</span>
              </div>
              <h3 className="text-sm font-medium text-white mb-2">No Connections</h3>
              <p className="text-sm text-gray-400">
                Connections will appear here as new content is analyzed against your notes.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {connections.map(c => (
                <ConnectionCard
                  key={c.connection_id}
                  conn={c}
                  onRate={rateConnection}
                  onDismiss={dismissConnection}
                  onPromote={promoteConnection}
                />
              ))}
            </div>
          )}
        </>
      )}

      {subTab === 'signals' && (
        <>
          {signals.length === 0 ? (
            <div className="text-center py-12">
              <div className="w-16 h-16 rounded-xl bg-gray-800 flex items-center justify-center mx-auto mb-4">
                <span className="text-3xl">📡</span>
              </div>
              <h3 className="text-sm font-medium text-white mb-2">No Unconnected Signals</h3>
              <p className="text-sm text-gray-400">
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
        </>
      )}
    </div>
  )
}
