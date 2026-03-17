import React, { useState, useEffect } from 'react'

const CATEGORIES = [
  { value: 'our_thesis', label: 'Our Thesis', color: 'text-amber-400' },
  { value: 'external_interview', label: 'External Interview', color: 'text-blue-400' },
]

function FeedCard({ feed, onDelete, onPoll }) {
  const catInfo = CATEGORIES.find(c => c.value === feed.category) || CATEGORIES[1]
  const isError = feed.status === 'error'

  return (
    <div className={`border rounded-lg p-4 ${isError ? 'border-red-800 bg-red-950/20' : 'border-gray-800 bg-gray-900/50'}`}>
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="font-medium text-white text-sm">{feed.display_name}</h3>
          <span className={`text-xs ${catInfo.color}`}>{catInfo.label}</span>
        </div>
        <div className="flex gap-1">
          <button onClick={() => onPoll(feed.feed_id)}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors">
            Poll
          </button>
          <button onClick={() => onDelete(feed.feed_id)}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-red-400 hover:bg-red-900/30 transition-colors">
            Remove
          </button>
        </div>
      </div>
      <p className="text-xs text-gray-500 truncate mb-2">{feed.url}</p>
      <div className="flex gap-4 text-xs text-gray-400">
        <span>{feed.item_count || 0} items</span>
        <span>Every {feed.poll_interval_minutes}min</span>
        {feed.last_fetched && <span>Last: {new Date(feed.last_fetched).toLocaleDateString()}</span>}
      </div>
      {isError && feed.last_error && (
        <p className="text-xs text-red-400 mt-2 truncate">{feed.last_error}</p>
      )}
      {feed.tags && feed.tags.length > 0 && (
        <div className="flex gap-1 mt-2">
          {feed.tags.map(t => (
            <span key={t} className="text-xs bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded">{t}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function PDFUploader({ onUploaded }) {
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const [sourceName, setSourceName] = useState('')
  const [author, setAuthor] = useState('')
  const [category, setCategory] = useState('external_interview')
  const [dragOver, setDragOver] = useState(false)

  async function handleUpload(files) {
    if (!files || files.length === 0) return
    setUploading(true)
    setResult(null)

    try {
      if (files.length === 1) {
        const formData = new FormData()
        formData.append('file', files[0])
        formData.append('category', category)
        if (sourceName) formData.append('source_name', sourceName)
        if (author) formData.append('author', author)

        const res = await fetch('/api/upload/pdf', { method: 'POST', body: formData })
        const data = await res.json()
        if (res.ok) {
          setResult({ success: true, message: `"${data.title}" queued for analysis (${data.pages} pages)` })
          onUploaded?.()
        } else {
          setResult({ success: false, message: data.detail || 'Upload failed' })
        }
      } else {
        const formData = new FormData()
        for (const f of files) formData.append('files', f)
        formData.append('category', category)
        if (sourceName) formData.append('source_name', sourceName)
        if (author) formData.append('author', author)

        const res = await fetch('/api/upload/pdf/batch', { method: 'POST', body: formData })
        const data = await res.json()
        if (res.ok) {
          setResult({ success: true, message: `${data.queued}/${data.total} PDFs queued for analysis` })
          onUploaded?.()
        } else {
          setResult({ success: false, message: data.detail || 'Batch upload failed' })
        }
      }
    } catch (e) {
      setResult({ success: false, message: e.message })
    } finally {
      setUploading(false)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'))
    if (files.length > 0) handleUpload(files)
  }

  return (
    <div>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <input type="text" value={sourceName} onChange={e => setSourceName(e.target.value)}
          placeholder="Source name (e.g. MacroAlf)"
          className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent" />
        <input type="text" value={author} onChange={e => setAuthor(e.target.value)}
          placeholder="Author (optional)"
          className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent" />
        <select value={category} onChange={e => setCategory(e.target.value)}
          className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-brand-accent">
          <option value="external_interview">External Interview</option>
          <option value="our_thesis">Our Thesis</option>
        </select>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById('pdf-file-input').click()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragOver ? 'border-brand-accent bg-brand-accent/10' :
          'border-gray-700 hover:border-gray-600 hover:bg-gray-900/30'
        }`}
      >
        <input id="pdf-file-input" type="file" accept=".pdf" multiple className="hidden"
          onChange={e => handleUpload(Array.from(e.target.files))} />
        {uploading ? (
          <p className="text-sm text-gray-400">Uploading and extracting text...</p>
        ) : (
          <>
            <p className="text-sm text-gray-300 mb-1">Drop PDFs here or click to browse</p>
            <p className="text-xs text-gray-500">Newsletters, research reports, investor letters · Max 50MB each</p>
          </>
        )}
      </div>

      {result && (
        <div className={`mt-3 text-sm px-3 py-2 rounded ${
          result.success ? 'bg-emerald-950/30 text-emerald-300 border border-emerald-800' :
          'bg-red-950/30 text-red-300 border border-red-800'
        }`}>
          {result.message}
        </div>
      )}
    </div>
  )
}

export default function Feeds() {
  const [feeds, setFeeds] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [newFeed, setNewFeed] = useState({ url: '', category: 'external_interview', display_name: '', tags: '' })
  const [addError, setAddError] = useState('')

  useEffect(() => { loadFeeds() }, [])

  async function loadFeeds() {
    try {
      const res = await fetch('/api/feeds/')
      setFeeds(await res.json())
    } catch (e) {
      console.error('Failed to load feeds:', e)
    } finally {
      setLoading(false)
    }
  }

  async function addFeed(e) {
    e.preventDefault()
    setAddError('')
    try {
      const body = {
        url: newFeed.url,
        category: newFeed.category,
        display_name: newFeed.display_name || null,
        tags: newFeed.tags ? newFeed.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
      }
      const res = await fetch('/api/feeds/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const err = await res.json()
        setAddError(err.detail || 'Failed to add feed')
        return
      }
      setShowAdd(false)
      setNewFeed({ url: '', category: 'external_interview', display_name: '', tags: '' })
      loadFeeds()
    } catch (e) {
      setAddError(e.message)
    }
  }

  async function deleteFeed(id) {
    if (!confirm('Delete this feed and all its content?')) return
    await fetch(`/api/feeds/${id}`, { method: 'DELETE' })
    loadFeeds()
  }

  async function pollFeed(id) {
    await fetch(`/api/feeds/${id}/poll`, { method: 'POST' })
    loadFeeds()
  }

  if (loading) return <div className="p-6 text-gray-400">Loading feeds...</div>

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-medium text-white">Feed Management</h2>
        <div className="flex gap-2">
          <button onClick={() => fetch('/api/feeds/poll', { method: 'POST' }).then(loadFeeds)}
            className="text-sm px-3 py-1.5 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors">
            Poll All
          </button>
          <button onClick={() => setShowAdd(!showAdd)}
            className="text-sm px-3 py-1.5 rounded bg-brand-accent text-white hover:bg-brand-accent/80 transition-colors">
            + Add Feed
          </button>
        </div>
      </div>

      {/* Add feed form */}
      {showAdd && (
        <form onSubmit={addFeed} className="border border-gray-800 rounded-lg p-4 mb-6 bg-gray-900/50">
          <div className="grid grid-cols-2 gap-3 mb-3">
            <input
              type="url" required placeholder="RSS/Atom feed URL"
              value={newFeed.url} onChange={e => setNewFeed(p => ({...p, url: e.target.value}))}
              className="col-span-2 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent"
            />
            <select
              value={newFeed.category} onChange={e => setNewFeed(p => ({...p, category: e.target.value}))}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-accent"
            >
              {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
            <input
              placeholder="Display name (optional)"
              value={newFeed.display_name} onChange={e => setNewFeed(p => ({...p, display_name: e.target.value}))}
              className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent"
            />
            <input
              placeholder="Tags (comma-separated)"
              value={newFeed.tags} onChange={e => setNewFeed(p => ({...p, tags: e.target.value}))}
              className="col-span-2 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent"
            />
          </div>
          {addError && <p className="text-sm text-red-400 mb-2">{addError}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowAdd(false)} className="text-sm px-3 py-1.5 rounded text-gray-400 hover:text-white">Cancel</button>
            <button type="submit" className="text-sm px-4 py-1.5 rounded bg-brand-accent text-white">Add Feed</button>
          </div>
        </form>
      )}

      {/* Feed list */}
      <div className="grid gap-3">
        {feeds.length === 0 ? (
          <p className="text-gray-500 text-sm">No feeds configured. Add your first RSS feed above.</p>
        ) : (
          feeds.map(f => <FeedCard key={f.feed_id} feed={f} onDelete={deleteFeed} onPoll={pollFeed} />)
        )}
      </div>

      {/* PDF Upload Section */}
      <div className="mt-8 border-t border-gray-800 pt-6">
        <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3">
          Upload PDF
          <span className="ml-2 text-xs text-gray-500 font-normal normal-case">
            Paid newsletters, research reports, investor letters
          </span>
        </h3>
        <PDFUploader onUploaded={loadFeeds} />
      </div>
    </div>
  )
}
