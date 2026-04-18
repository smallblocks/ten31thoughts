import React, { useState, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

const RELATION_OPTIONS = [
  { value: '', label: 'All Relations' },
  { value: 'reinforces', label: 'Reinforces' },
  { value: 'extends', label: 'Extends' },
  { value: 'complicates', label: 'Complicates' },
  { value: 'contradicts', label: 'Contradicts' },
  { value: 'echoes_mechanism', label: 'Echoes Mechanism' },
]

const RELATION_COLORS = {
  reinforces: 'bg-emerald-500 text-white',
  extends: 'bg-blue-500 text-white',
  complicates: 'bg-amber-500 text-white',
  contradicts: 'bg-brand-accent text-white',
  echoes_mechanism: 'bg-purple-500 text-white',
}

function RelationBadge({ relation }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${RELATION_COLORS[relation] || 'bg-gray-800 text-gray-400'}`}>
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
      <span className="text-xs text-text-secondary font-mono w-8 text-right">{pct}%</span>
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
    <div className="border border-border rounded-lg p-4 bg-surface">
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            {conn.item_title ? (
              <a href={conn.item_url} target="_blank" rel="noopener noreferrer"
                className="text-sm font-medium text-text-primary hover:text-brand-accent transition-colors">
                {conn.item_title}
              </a>
            ) : (
              <span className="text-sm text-text-secondary">Unknown source</span>
            )}
            <RelationBadge relation={conn.relation} />
          </div>
          
          {/* Full articulation */}
          <p className="text-sm text-text-primary leading-relaxed mb-3">{conn.articulation}</p>
          
          {/* Excerpt */}
          {conn.excerpt && (
            <blockquote className="border-l-2 border-border pl-3 mb-3">
              <p className="text-xs text-text-secondary italic font-serif">{conn.excerpt}</p>
              {conn.excerpt_location && (
                <cite className="text-xs text-text-secondary not-italic font-mono">
                  {conn.excerpt_location}
                </cite>
              )}
            </blockquote>
          )}
          
          {/* Target note preview */}
          {notePreview && (
            <p className="text-xs text-text-secondary mb-3">
              → <strong>{conn.note_title || 'Note'}:</strong> {notePreview}
            </p>
          )}
        </div>
      </div>

      {/* Principles */}
      {conn.principles_invoked && conn.principles_invoked.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {conn.principles_invoked.map((p, i) => (
            <span key={i} className="text-xs bg-gray-800 text-text-secondary px-2 py-0.5 rounded">
              {typeof p === 'string' ? p : p.name || p.principle || JSON.stringify(p)}
            </span>
          ))}
        </div>
      )}

      {/* Strength */}
      <div className="mb-3">
        <StrengthBar strength={conn.strength} />
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <StarRating 
          current={conn.user_rating} 
          onRate={rating => onRate(conn.connection_id, rating)} 
        />
        <div className="flex items-center gap-2">
          <button 
            onClick={() => onPromote(conn.connection_id)}
            className="text-xs px-3 py-1 rounded bg-emerald-800 text-emerald-200 hover:bg-emerald-700 transition-colors"
            title="Promote to Note"
          >
            → Note
          </button>
          <button 
            onClick={() => onDismiss(conn.connection_id)}
            className="text-xs px-3 py-1 rounded bg-gray-800 text-red-400 hover:bg-red-900/30 transition-colors"
            title="Dismiss"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Connections() {
  const [connections, setConnections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const location = useLocation()

  // Filters
  const [filterRelation, setFilterRelation] = useState('')
  const [minStrength, setMinStrength] = useState(0)
  const [maxStrength, setMaxStrength] = useState(1)
  const [showDismissed, setShowDismissed] = useState(false)
  const [showRated, setShowRated] = useState(true)

  // Check if we should show only unrated from URL params
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    if (params.get('unrated') === 'true') {
      setShowRated(false)
    }
  }, [location])

  useEffect(() => {
    loadConnections()
  }, [filterRelation, minStrength, maxStrength, showDismissed, showRated])

  async function loadConnections() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (filterRelation) params.set('relation', filterRelation)
      if (minStrength > 0) params.set('min_strength', minStrength)
      if (!showRated) params.set('unrated', 'true')
      if (showDismissed) params.set('dismissed', 'true')
      params.set('limit', '100')

      const res = await fetch(`/api/connections/?${params}`)
      if (!res.ok) throw new Error('Failed to load connections')
      
      let data = await res.json()
      
      // Client-side strength filter for max
      if (maxStrength < 1) {
        data = data.filter(c => c.strength == null || c.strength <= maxStrength)
      }
      
      setConnections(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function rateConnection(id, rating) {
    try {
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
    } catch (e) {
      console.error('Failed to rate connection:', e)
    }
  }

  async function dismissConnection(id) {
    try {
      const res = await fetch(`/api/connections/${id}`, { method: 'DELETE' })
      if (res.ok || res.status === 204) {
        setConnections(prev => prev.filter(c => c.connection_id !== id))
      }
    } catch (e) {
      console.error('Failed to dismiss connection:', e)
    }
  }

  async function promoteConnection(id) {
    try {
      const res = await fetch(`/api/connections/${id}/promote`, { method: 'POST' })
      if (res.ok) {
        setConnections(prev =>
          prev.map(c => c.connection_id === id ? { ...c, user_promoted_to_note: true } : c)
        )
      }
    } catch (e) {
      console.error('Failed to promote connection:', e)
    }
  }

  if (loading) return <div className="p-6 text-text-secondary">Loading connections...</div>
  if (error) return <div className="p-6 text-red-400">Error: {error}</div>

  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-medium text-text-primary">Connections</h2>
          <p className="text-sm text-text-secondary">
            Review how new content relates to your notes ({connections.length} shown)
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <select
          value={filterRelation}
          onChange={e => setFilterRelation(e.target.value)}
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand-accent"
        >
          {RELATION_OPTIONS.map(r => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
        
        <div className="flex items-center gap-2">
          <label className="text-xs text-text-secondary">Strength:</label>
          <input
            type="range"
            min="0" max="1" step="0.05"
            value={minStrength}
            onChange={e => setMinStrength(parseFloat(e.target.value))}
            className="w-16"
          />
          <span className="text-xs font-mono text-text-secondary w-8">
            {Math.round(minStrength * 100)}%
          </span>
          <span className="text-xs text-text-secondary">to</span>
          <input
            type="range"
            min="0" max="1" step="0.05"
            value={maxStrength}
            onChange={e => setMaxStrength(parseFloat(e.target.value))}
            className="w-16"
          />
          <span className="text-xs font-mono text-text-secondary w-8">
            {Math.round(maxStrength * 100)}%
          </span>
        </div>
        
        <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={showRated}
            onChange={e => setShowRated(e.target.checked)}
            className="rounded bg-surface border-border"
          />
          Show rated
        </label>
        
        <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={showDismissed}
            onChange={e => setShowDismissed(e.target.checked)}
            className="rounded bg-surface border-border"
          />
          Show dismissed
        </label>
      </div>

      {/* Connections list */}
      {connections.length === 0 ? (
        <div className="text-center py-12">
          <h3 className="text-sm font-medium text-text-primary mb-2">No connections found</h3>
          <p className="text-sm text-text-secondary">
            Connections will appear here as new content is analyzed against your notes.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {connections
            .sort((a, b) => (b.strength || 0) - (a.strength || 0)) // Sort by strength descending
            .map(c => (
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
    </div>
  )
}