import React, { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'

const TOPICS = [
  'monetary_policy', 'bitcoin_adoption', 'mining_energy', 'regulation',
  'macro_liquidity', 'geopolitics', 'technology', 'market_structure',
  'defi_stablecoins', 'sovereignty', 'other',
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
    reinforces: 'bg-emerald-500 text-white',
    extends: 'bg-blue-500 text-white',
    complicates: 'bg-amber-500 text-white',
    contradicts: 'bg-brand-accent text-white',
    echoes_mechanism: 'bg-purple-500 text-white',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${colors[relation] || 'bg-gray-800 text-gray-400'}`}>
      {relation.replace(/_/g, ' ')}
    </span>
  )
}

function ConnectionCard({ conn }) {
  return (
    <div className="border border-border rounded-lg p-3 bg-surface">
      <div className="flex items-start gap-2 mb-2">
        {conn.item_title ? (
          <a href={conn.item_url} target="_blank" rel="noopener noreferrer"
            className="text-sm font-medium text-text-primary hover:text-brand-accent transition-colors flex-1">
            {conn.item_title}
          </a>
        ) : (
          <span className="text-sm text-text-secondary flex-1">Unknown source</span>
        )}
        <RelationBadge relation={conn.relation} />
      </div>
      <p className="text-xs text-text-primary mb-2">{conn.articulation}</p>
      {conn.excerpt && (
        <blockquote className="border-l-2 border-border pl-3">
          <p className="text-xs text-text-secondary italic">{conn.excerpt}</p>
        </blockquote>
      )}
    </div>
  )
}

function EditForm({ note, onSave, onCancel }) {
  const [title, setTitle] = useState(note.title || '')
  const [body, setBody] = useState(note.body || '')
  const [topic, setTopic] = useState(note.topic || '')
  const [tags, setTags] = useState((note.tags || []).join(', '))
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!body.trim()) return
    
    setSaving(true)
    try {
      await onSave({
        title: title.trim() || null,
        body: body.trim(),
        topic: topic || null,
        tags: tags ? tags.split(',').map(t => t.trim()).filter(Boolean) : [],
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <input
        type="text"
        value={title}
        onChange={e => setTitle(e.target.value)}
        placeholder="Title (optional)"
        className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent"
      />
      
      <textarea
        value={body}
        onChange={e => setBody(e.target.value)}
        placeholder="Note body (required)"
        rows={12}
        required
        className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent resize-y"
      />
      
      <div className="grid grid-cols-2 gap-3">
        <select
          value={topic}
          onChange={e => setTopic(e.target.value)}
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand-accent"
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
          className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent"
        />
      </div>
      
      <div className="flex justify-end gap-2">
        <button 
          type="button" 
          onClick={onCancel}
          className="text-sm px-3 py-2 rounded text-text-secondary hover:text-text-primary transition-colors"
        >
          Cancel
        </button>
        <button 
          type="submit" 
          disabled={saving || !body.trim()}
          className="text-sm px-4 py-2 rounded bg-brand-accent text-white hover:bg-red-500 disabled:bg-gray-700 disabled:text-gray-500 transition-colors"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  )
}

export default function NoteDetail() {
  const { noteId } = useParams()
  const navigate = useNavigate()
  const [note, setNote] = useState(null)
  const [connections, setConnections] = useState([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadNote()
  }, [noteId])

  async function loadNote() {
    setLoading(true)
    setError(null)
    try {
      const [noteRes, connRes] = await Promise.all([
        fetch(`/api/notes/${noteId}`),
        fetch(`/api/connections/?note_id=${noteId}`),
      ])
      
      if (!noteRes.ok) {
        if (noteRes.status === 404) {
          setError('Note not found')
        } else {
          throw new Error('Failed to load note')
        }
        return
      }
      
      setNote(await noteRes.json())
      
      if (connRes.ok) {
        setConnections(await connRes.json())
      } else {
        setConnections([])
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function saveNote(data) {
    const res = await fetch(`/api/notes/${noteId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Failed to update note')
    }
    
    setEditing(false)
    await loadNote()
  }

  async function archiveNote() {
    if (!confirm('Archive this note?')) return
    
    const res = await fetch(`/api/notes/${noteId}`, { method: 'DELETE' })
    if (res.ok || res.status === 204) {
      navigate('/notes')
    }
  }

  async function restoreNote() {
    const res = await fetch(`/api/notes/${noteId}/restore`, { method: 'POST' })
    if (res.ok || res.status === 204) {
      await loadNote()
    }
  }

  if (loading) return <div className="p-6 text-text-secondary">Loading note...</div>
  if (error) return (
    <div className="p-6">
      <div className="text-red-400 mb-4">Error: {error}</div>
      <Link to="/notes" className="text-sm text-brand-accent hover:text-red-400">
        ← Back to Notes
      </Link>
    </div>
  )

  // Group connections by relation
  const connectionsByRelation = connections.reduce((acc, conn) => {
    const relation = conn.relation || 'unknown'
    if (!acc[relation]) acc[relation] = []
    acc[relation].push(conn)
    return acc
  }, {})

  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
      <Link to="/notes" className="text-sm text-text-secondary hover:text-text-primary mb-4 inline-flex items-center gap-1">
        ← All Notes
      </Link>

      <div className="border border-border rounded-lg p-6 bg-surface mb-6">
        {editing ? (
          <EditForm 
            note={note} 
            onSave={saveNote} 
            onCancel={() => setEditing(false)} 
          />
        ) : (
          <>
            <div className="flex items-start justify-between mb-4">
              <div className="flex-1">
                {note.title && (
                  <h1 className="text-xl font-medium text-text-primary mb-3">{note.title}</h1>
                )}
                <div className="flex flex-wrap items-center gap-2 mb-4">
                  <TopicBadge topic={note.topic} />
                  <SourceBadge source={note.source} />
                  {(note.tags || []).map(t => <TagChip key={t} tag={t} />)}
                  <span className="text-xs font-mono text-text-secondary">
                    Created {new Date(note.created_at).toLocaleDateString()}
                  </span>
                  {note.updated_at && note.updated_at !== note.created_at && (
                    <span className="text-xs font-mono text-text-secondary">
                      Updated {new Date(note.updated_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                
                {/* Thread context */}
                {(note.tags || []).some(tag => tag.startsWith('thread:')) && (
                  <div className="mb-4 p-3 bg-purple-900/20 border border-purple-800 rounded">
                    <p className="text-xs text-purple-300">
                      Thread: {(note.tags || []).find(tag => tag.startsWith('thread:'))?.slice(7)}
                    </p>
                  </div>
                )}
              </div>
              
              <div className="flex gap-2">
                <button 
                  onClick={() => setEditing(true)}
                  className="text-sm px-3 py-2 rounded bg-gray-800 text-text-primary hover:bg-gray-700 transition-colors"
                >
                  Edit
                </button>
                {note.archived ? (
                  <button 
                    onClick={restoreNote}
                    className="text-sm px-3 py-2 rounded bg-emerald-800 text-emerald-200 hover:bg-emerald-700 transition-colors"
                  >
                    Restore
                  </button>
                ) : (
                  <button 
                    onClick={archiveNote}
                    className="text-sm px-3 py-2 rounded bg-gray-800 text-red-400 hover:bg-red-900/30 transition-colors"
                  >
                    Archive
                  </button>
                )}
              </div>
            </div>
            
            <div>
              <p className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">{note.body}</p>
            </div>
          </>
        )}
      </div>

      {/* Connections */}
      <div className="space-y-6">
        <div>
          <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wider mb-3">
            Connections to this note
          </h3>
          
          {connections.length === 0 ? (
            <p className="text-sm text-text-secondary">No connections found for this note.</p>
          ) : (
            <div className="space-y-4">
              {Object.entries(connectionsByRelation).map(([relation, conns]) => (
                <div key={relation}>
                  <h4 className="text-sm font-medium text-text-primary mb-2 capitalize">
                    {relation.replace(/_/g, ' ')} ({conns.length})
                  </h4>
                  <div className="space-y-2">
                    {conns.map(conn => (
                      <ConnectionCard key={conn.connection_id} conn={conn} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Resurfacing history placeholder */}
        <div>
          <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wider mb-3">
            Resurfacing History
          </h3>
          <p className="text-sm text-text-secondary">
            Resurfacing history not yet available via API.
          </p>
        </div>
      </div>
    </div>
  )
}