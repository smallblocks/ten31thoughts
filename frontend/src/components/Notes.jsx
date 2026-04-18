import React, { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'

const TOPICS = [
  'monetary_policy', 'bitcoin_adoption', 'mining_energy', 'regulation',
  'macro_liquidity', 'geopolitics', 'technology', 'market_structure',
  'defi_stablecoins', 'sovereignty', 'other',
]

const SOURCE_OPTIONS = [
  { value: '', label: 'All Sources' },
  { value: 'manual', label: 'Manual' },
  { value: 'timestamp', label: 'Timestamp (legacy)' },
  { value: 'timestamp_synopsis', label: 'Timestamp Synopsis' },
  { value: 'promoted_from_connection', label: 'From Connection' },
  { value: 'promoted_from_signal', label: 'From Signal' },
]

function TopicBadge({ topic }) {
  if (!topic) return null
  return (
    <span className="text-xs bg-purple-900/40 text-purple-300 border border-purple-800 px-2 py-0.5 rounded">
      {topic.replace(/_/g, ' ')}
    </span>
  )
}

function TagChip({ tag }) {
  return (
    <span className="text-xs bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">
      {tag}
    </span>
  )
}

function TierBadge({ tier }) {
  if (!tier) return null
  const colors = {
    axiom: 'bg-red-900/40 text-red-300 border-red-800',
    thesis: 'bg-amber-900/40 text-amber-300 border-amber-800',
    observation: 'bg-gray-700 text-gray-300 border-gray-600',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${colors[tier] || 'bg-gray-800 text-gray-400 border-gray-700'}`}>
      {tier}
    </span>
  )
}

function SourceBadge({ source }) {
  if (!source) return null
  const colors = {
    manual: 'bg-blue-900/40 text-blue-300 border-blue-800',
    timestamp: 'bg-amber-900/40 text-amber-300 border-amber-800',
    timestamp_synopsis: 'bg-amber-900/40 text-amber-300 border-amber-800',
    promoted_from_connection: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
    promoted_from_signal: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${colors[source] || 'bg-gray-800 text-gray-400 border-gray-700'}`}>
      {source.replace(/_/g, ' ')}
    </span>
  )
}

function NoteCard({ note, onClick }) {
  const title = note.title || note.body.split('\n')[0].slice(0, 60) + (note.body.length > 60 ? '...' : '')
  const bodyPreview = note.body.length > 200 ? note.body.slice(0, 200) + '…' : note.body

  return (
    <button
      onClick={onClick}
      className="w-full text-left border border-border rounded-lg p-3 bg-surface hover:bg-gray-800 transition-colors"
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          <h4 className="text-sm font-medium text-text-primary mb-1 line-clamp-1">
            {title}
          </h4>
          <p className="text-xs text-text-secondary leading-relaxed line-clamp-2">
            {bodyPreview}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <TopicBadge topic={note.topic} />
        <SourceBadge source={note.source} />
        <TierBadge tier={note.conviction_tier} />
        {(note.tags || []).slice(0, 3).map(t => <TagChip key={t} tag={t} />)}
        {(note.tags || []).length > 3 && (
          <span className="text-xs text-text-secondary">+{(note.tags || []).length - 3}</span>
        )}
        <span className="text-xs font-mono text-text-secondary ml-auto">
          {new Date(note.created_at).toLocaleDateString()}
        </span>
      </div>
    </button>
  )
}

export default function Notes() {
  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  // Filters
  const [search, setSearch] = useState('')
  const [filterTopic, setFilterTopic] = useState('')
  const [filterTag, setFilterTag] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [filterTier, setFilterTier] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [sortBy, setSortBy] = useState('recent')

  useEffect(() => {
    loadNotes()
  }, [filterTopic, filterTag, showArchived])

  async function loadNotes() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (filterTopic) params.set('topic', filterTopic)
      if (filterTag) params.set('tag', filterTag)
      params.set('archived', showArchived)
      params.set('limit', '100')

      const res = await fetch(`/api/notes/?${params}`)
      if (!res.ok) throw new Error('Failed to load notes')
      let data = await res.json()

      // Client-side filters
      if (filterSource) {
        data = data.filter(n => (n.source || 'manual') === filterSource)
      }
      if (filterTier) {
        data = data.filter(n => n.conviction_tier === filterTier)
      }
      if (search) {
        const searchLower = search.toLowerCase()
        data = data.filter(n => 
          (n.title?.toLowerCase().includes(searchLower)) ||
          (n.body?.toLowerCase().includes(searchLower)) ||
          (n.tags || []).some(tag => tag.toLowerCase().includes(searchLower))
        )
      }

      // Sort
      if (sortBy === 'recent') {
        data.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      } else if (sortBy === 'topic') {
        data.sort((a, b) => (a.topic || 'zzz').localeCompare(b.topic || 'zzz'))
      }

      setNotes(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="p-6 text-text-secondary">Loading notes...</div>
  if (error) return <div className="p-6 text-red-400">Error: {error}</div>

  return (
    <div className="p-6 max-w-6xl mx-auto overflow-y-auto h-full">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-medium text-text-primary">Notes</h2>
          <p className="text-sm text-text-secondary">{notes.length} note{notes.length !== 1 ? 's' : ''}</p>
        </div>
      </div>

      {/* Search */}
      <div className="mb-4">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search notes..."
          className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <select
          value={filterTopic}
          onChange={e => setFilterTopic(e.target.value)}
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand-accent"
        >
          <option value="">All Topics</option>
          {TOPICS.map(t => (
            <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
          ))}
        </select>
        
        <input
          type="text"
          value={filterTag}
          onChange={e => setFilterTag(e.target.value)}
          placeholder="Filter by tag"
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent"
        />
        
        <select
          value={filterSource}
          onChange={e => setFilterSource(e.target.value)}
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand-accent"
        >
          {SOURCE_OPTIONS.map(s => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>

        <select
          value={filterTier}
          onChange={e => setFilterTier(e.target.value)}
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand-accent"
        >
          <option value="">All Tiers</option>
          <option value="axiom">Axiom</option>
          <option value="thesis">Thesis</option>
          <option value="observation">Observation</option>
        </select>

        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand-accent"
        >
          <option value="recent">Recent</option>
          <option value="topic">By Topic</option>
        </select>
        
        <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={e => setShowArchived(e.target.checked)}
            className="rounded bg-surface border-border"
          />
          Show archived
        </label>
      </div>

      {/* Note list */}
      {notes.length === 0 ? (
        <div className="text-center py-12">
          <h3 className="text-sm font-medium text-text-primary mb-2">No notes match</h3>
          <p className="text-sm text-text-secondary max-w-md mx-auto">
            Notes come from four places: Timestamp issues, promoted connections, promoted signals, and manual entry.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {notes.map(note => (
            <NoteCard
              key={note.note_id}
              note={note}
              onClick={() => navigate(`/notes/${note.note_id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}