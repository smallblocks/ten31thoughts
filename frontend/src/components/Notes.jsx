import React, { useState, useEffect } from 'react'

const TOPICS = [
  'monetary_policy', 'bitcoin_adoption', 'mining_energy', 'regulation',
  'macro_liquidity', 'geopolitics', 'technology', 'market_structure',
  'defi_stablecoins', 'sovereignty', 'other',
]

const SOURCE_OPTIONS = [
  { value: '', label: 'All Sources' },
  { value: 'manual', label: 'Manual' },
  { value: 'timestamp', label: 'Timestamp' },
  { value: 'promoted', label: 'Promoted' },
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

function SourceBadge({ source }) {
  if (!source) return null
  const colors = {
    manual: 'bg-blue-900/40 text-blue-300 border-blue-800',
    timestamp: 'bg-amber-900/40 text-amber-300 border-amber-800',
    promoted: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
    promoted_from_connection: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
    promoted_from_signal: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${colors[source] || 'bg-gray-800 text-gray-400 border-gray-700'}`}>
      {source.replace(/_/g, ' ')}
    </span>
  )
}

function RelationBadge({ relation }) {
  const colors = {
    reinforces: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
    extends: 'bg-blue-900/40 text-blue-300 border-blue-800',
    complicates: 'bg-amber-900/40 text-amber-300 border-amber-800',
    contradicts: 'bg-red-900/40 text-red-300 border-red-800',
    echoes_mechanism: 'bg-purple-900/40 text-purple-300 border-purple-800',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${colors[relation] || 'bg-gray-800 text-gray-400 border-gray-700'}`}>
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

function NoteCard({ note, onClick }) {
  const bodyPreview = note.body.length > 200 ? note.body.slice(0, 200) + '…' : note.body
  return (
    <button
      onClick={onClick}
      className="w-full text-left border border-gray-800 rounded-lg p-4 bg-gray-900/20 hover:bg-gray-900/50 hover:border-gray-700 transition-colors"
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          {note.title && (
            <h4 className="text-sm font-medium text-white mb-1">{note.title}</h4>
          )}
          <p className="text-xs text-gray-300 leading-relaxed">{bodyPreview}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-2">
        <TopicBadge topic={note.topic} />
        <SourceBadge source={note.source} />
        {(note.tags || []).map(t => <TagChip key={t} tag={t} />)}
        <span className="text-xs text-gray-600 ml-auto">
          {new Date(note.created_at).toLocaleDateString()}
        </span>
      </div>
    </button>
  )
}

function ConnectionCard({ conn }) {
  return (
    <div className="border border-gray-800 rounded-lg p-3 bg-gray-900/20">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          {conn.item_title && (
            <a href={conn.item_url} target="_blank" rel="noopener noreferrer"
              className="text-sm text-white hover:text-brand-accent transition-colors">
              {conn.item_title}
            </a>
          )}
          <RelationBadge relation={conn.relation} />
        </div>
      </div>
      <p className="text-xs text-gray-300 mb-2">{conn.articulation}</p>
      <StrengthBar strength={conn.strength} />
    </div>
  )
}

function NoteForm({ onSubmit, onCancel, initial }) {
  const [body, setBody] = useState(initial?.body || '')
  const [title, setTitle] = useState(initial?.title || '')
  const [topic, setTopic] = useState(initial?.topic || '')
  const [tags, setTags] = useState(initial?.tags?.join(', ') || '')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!body.trim()) return
    setSaving(true)
    try {
      await onSubmit({
        body: body.trim(),
        title: title.trim() || null,
        topic: topic || null,
        tags: tags ? tags.split(',').map(t => t.trim()).filter(Boolean) : [],
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="border border-gray-800 rounded-lg p-4 mb-6 bg-gray-900/50">
      <div className="space-y-3">
        <input
          type="text"
          value={title}
          onChange={e => setTitle(e.target.value)}
          placeholder="Title (optional)"
          className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent"
        />
        <textarea
          value={body}
          onChange={e => setBody(e.target.value)}
          placeholder="Note body (required)"
          rows={4}
          required
          className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent resize-y"
        />
        <div className="grid grid-cols-2 gap-3">
          <select
            value={topic}
            onChange={e => setTopic(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-brand-accent"
          >
            <option value="">No topic</option>
            {TOPICS.map(t => (
              <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
            ))}
          </select>
          <input
            type="text"
            value={tags}
            onChange={e => setTags(e.target.value)}
            placeholder="Tags (comma-separated)"
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent"
          />
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <button type="button" onClick={onCancel}
          className="text-sm px-3 py-1.5 rounded text-gray-400 hover:text-white transition-colors">
          Cancel
        </button>
        <button type="submit" disabled={saving || !body.trim()}
          className="text-sm px-4 py-1.5 rounded bg-brand-accent text-white hover:bg-brand-accent/80 disabled:bg-gray-700 disabled:text-gray-500 transition-colors">
          {saving ? 'Saving…' : (initial ? 'Update' : 'Add Note')}
        </button>
      </div>
    </form>
  )
}

export default function Notes() {
  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showAdd, setShowAdd] = useState(false)

  // Filters
  const [filterTopic, setFilterTopic] = useState('')
  const [filterTag, setFilterTag] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [showArchived, setShowArchived] = useState(false)

  // Detail view
  const [selectedNote, setSelectedNote] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [connections, setConnections] = useState([])

  useEffect(() => { loadNotes() }, [filterTopic, filterTag, showArchived])

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

      // Client-side source filter (API doesn't have source filter)
      if (filterSource) {
        data = data.filter(n => (n.source || 'manual') === filterSource)
      }

      setNotes(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadNoteDetail(noteId) {
    setDetailLoading(true)
    try {
      const [noteRes, connRes] = await Promise.all([
        fetch(`/api/notes/${noteId}`),
        fetch(`/api/connections/?note_id=${noteId}`),
      ])
      if (noteRes.ok) setSelectedNote(await noteRes.json())
      if (connRes.ok) setConnections(await connRes.json())
      else setConnections([])
    } catch (e) {
      console.error('Failed to load note detail:', e)
    } finally {
      setDetailLoading(false)
    }
  }

  async function createNote(data) {
    const res = await fetch('/api/notes/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Failed to create note')
    }
    setShowAdd(false)
    loadNotes()
  }

  async function updateNote(data) {
    const res = await fetch(`/api/notes/${selectedNote.note_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Failed to update note')
    }
    setEditing(false)
    loadNoteDetail(selectedNote.note_id)
    loadNotes()
  }

  async function archiveNote() {
    if (!confirm('Archive this note?')) return
    const res = await fetch(`/api/notes/${selectedNote.note_id}`, { method: 'DELETE' })
    if (res.ok || res.status === 204) {
      setSelectedNote(null)
      loadNotes()
    }
  }

  // ─── Detail view ───
  if (selectedNote && !detailLoading) {
    if (editing) {
      return (
        <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
          <button onClick={() => setEditing(false)}
            className="text-sm text-gray-400 hover:text-white mb-4 flex items-center gap-1">
            ← Cancel Edit
          </button>
          <NoteForm
            initial={selectedNote}
            onSubmit={updateNote}
            onCancel={() => setEditing(false)}
          />
        </div>
      )
    }

    return (
      <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
        <button onClick={() => setSelectedNote(null)}
          className="text-sm text-gray-400 hover:text-white mb-4 flex items-center gap-1">
          ← All Notes
        </button>

        <div className="border border-gray-800 rounded-lg p-6 bg-gray-900/30 mb-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              {selectedNote.title && (
                <h2 className="text-lg font-medium text-white mb-2">{selectedNote.title}</h2>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <TopicBadge topic={selectedNote.topic} />
                <SourceBadge source={selectedNote.source} />
                {(selectedNote.tags || []).map(t => <TagChip key={t} tag={t} />)}
                <span className="text-xs text-gray-600">
                  Created {new Date(selectedNote.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setEditing(true)}
                className="text-sm px-3 py-1.5 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors">
                Edit
              </button>
              <button onClick={archiveNote}
                className="text-sm px-3 py-1.5 rounded bg-gray-800 text-red-400 hover:bg-red-900/30 transition-colors">
                Archive
              </button>
            </div>
          </div>
          <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">{selectedNote.body}</p>
        </div>

        {/* Connections to this note */}
        <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3">
          Connections to this note
        </h3>
        {connections.length > 0 ? (
          <div className="space-y-2">
            {connections.map(c => (
              <ConnectionCard key={c.connection_id} conn={c} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500">No connections found for this note.</p>
        )}
      </div>
    )
  }

  if (detailLoading) {
    return <div className="p-6 text-gray-400">Loading note...</div>
  }

  // ─── List view ───
  if (loading) return <div className="p-6 text-gray-400">Loading notes...</div>
  if (error) return <div className="p-6 text-red-400">Error: {error}</div>

  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-medium text-white">Notes</h2>
          <p className="text-sm text-gray-500">{notes.length} note{notes.length !== 1 ? 's' : ''}</p>
        </div>
        <button onClick={() => setShowAdd(!showAdd)}
          className="text-sm px-3 py-1.5 rounded bg-brand-accent text-white hover:bg-brand-accent/80 transition-colors">
          + Add Note
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <NoteForm onSubmit={createNote} onCancel={() => setShowAdd(false)} />
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={filterTopic}
          onChange={e => setFilterTopic(e.target.value)}
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-brand-accent"
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
          onKeyDown={e => { if (e.key === 'Enter') loadNotes() }}
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent"
        />
        <select
          value={filterSource}
          onChange={e => { setFilterSource(e.target.value); }}
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-brand-accent"
        >
          {SOURCE_OPTIONS.map(s => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={e => setShowArchived(e.target.checked)}
            className="rounded bg-gray-800 border-gray-700"
          />
          Show archived
        </label>
      </div>

      {/* Note list */}
      {notes.length === 0 ? (
        <div className="text-center py-12">
          <div className="w-16 h-16 rounded-xl bg-gray-800 flex items-center justify-center mx-auto mb-4">
            <span className="text-3xl">📝</span>
          </div>
          <h3 className="text-sm font-medium text-white mb-2">No Notes Yet</h3>
          <p className="text-sm text-gray-400">
            Add your first note above, or notes will appear here as connections get promoted.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {notes.map(n => (
            <NoteCard
              key={n.note_id}
              note={n}
              onClick={() => loadNoteDetail(n.note_id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
