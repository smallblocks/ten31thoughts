import React, { useState, useEffect } from 'react'

const CATEGORIES = [
  { value: 'our_thesis', label: 'Our Thesis', color: 'text-amber-400' },
  { value: 'external_interview', label: 'External Interview', color: 'text-blue-400' },
]

function FeedCard({ feed, onDelete, onPoll }) {
  const catInfo = CATEGORIES.find(c => c.value === feed.category) || CATEGORIES[1]
  const isError = feed.status === 'error'

  return (
    <div className={`border rounded-lg p-3 ${
      isError 
        ? 'border-red-800 bg-red-950/20' 
        : 'border-border bg-surface'
    }`}>
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="font-medium text-text-primary text-sm">{feed.display_name}</h3>
          <span className={`text-xs ${catInfo.color}`}>{catInfo.label}</span>
        </div>
        <div className="flex gap-1">
          <button 
            onClick={() => onPoll(feed.feed_id)}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-text-secondary hover:bg-gray-700 transition-colors"
          >
            Poll
          </button>
          <button 
            onClick={() => onDelete(feed.feed_id)}
            className="text-xs px-2 py-1 rounded bg-gray-800 text-red-400 hover:bg-red-900/30 transition-colors"
          >
            Remove
          </button>
        </div>
      </div>
      
      <p className="text-xs text-text-secondary truncate mb-2">{feed.url}</p>
      
      <div className="flex gap-4 text-xs text-text-secondary">
        <span>{feed.item_count || 0} items</span>
        <span>Every {feed.poll_interval_minutes}min</span>
        {feed.last_fetched && (
          <span>Last: {new Date(feed.last_fetched).toLocaleDateString()}</span>
        )}
      </div>
      
      {isError && feed.last_error && (
        <p className="text-xs text-red-400 mt-2 truncate">{feed.last_error}</p>
      )}
      
      {feed.tags && feed.tags.length > 0 && (
        <div className="flex gap-1 mt-2">
          {feed.tags.map(t => (
            <span key={t} className="text-xs bg-gray-800 text-text-secondary px-1.5 py-0.5 rounded">
              {t}
            </span>
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
          setResult({ 
            success: true, 
            message: `"${data.title}" queued for analysis (${data.pages} pages)` 
          })
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
          setResult({ 
            success: true, 
            message: `${data.queued}/${data.total} PDFs queued for analysis` 
          })
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
    const files = Array.from(e.dataTransfer.files).filter(f => 
      f.name.toLowerCase().endsWith('.pdf')
    )
    if (files.length > 0) handleUpload(files)
  }

  return (
    <div>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <input 
          type="text" 
          value={sourceName} 
          onChange={e => setSourceName(e.target.value)}
          placeholder="Source name (e.g. MacroAlf)"
          className="bg-surface border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent" 
        />
        <input 
          type="text" 
          value={author} 
          onChange={e => setAuthor(e.target.value)}
          placeholder="Author (optional)"
          className="bg-surface border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent" 
        />
        <select 
          value={category} 
          onChange={e => setCategory(e.target.value)}
          className="bg-surface border border-border rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand-accent"
        >
          <option value="external_interview">External Interview</option>
          <option value="our_thesis">Our Thesis</option>
        </select>
      </div>

      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById('pdf-file-input').click()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragOver 
            ? 'border-brand-accent bg-brand-accent/10' 
            : 'border-border hover:border-gray-600 hover:bg-gray-900/30'
        }`}
      >
        <input 
          id="pdf-file-input" 
          type="file" 
          accept=".pdf" 
          multiple 
          className="hidden"
          onChange={e => handleUpload(Array.from(e.target.files))} 
        />
        {uploading ? (
          <p className="text-sm text-text-secondary">Uploading and extracting text...</p>
        ) : (
          <>
            <p className="text-sm text-text-primary mb-1">Drop PDFs here or click to browse</p>
            <p className="text-xs text-text-secondary">
              Newsletters, research reports, investor letters · Max 50MB each
            </p>
          </>
        )}
      </div>

      {result && (
        <div className={`mt-3 text-sm px-3 py-2 rounded ${
          result.success 
            ? 'bg-emerald-950/30 text-emerald-300 border border-emerald-800' 
            : 'bg-red-950/30 text-red-300 border border-red-800'
        }`}>
          {result.message}
        </div>
      )}
    </div>
  )
}

function IngestStatus({ analysisQueue }) {
  if (!analysisQueue) return null

  const total = Object.values(analysisQueue).reduce((sum, count) => sum + count, 0)

  return (
    <div className="border border-border rounded-lg p-4 bg-surface">
      <h4 className="text-sm font-medium text-text-primary mb-3">Analysis Queue</h4>
      
      {total === 0 ? (
        <p className="text-xs text-text-secondary">No items in analysis queue</p>
      ) : (
        <div className="space-y-2">
          {Object.entries(analysisQueue).map(([status, count]) => {
            if (count === 0) return null
            
            const colors = {
              pending: 'text-amber-400',
              analyzing: 'text-blue-400', 
              complete: 'text-emerald-400',
              error: 'text-red-400'
            }
            
            return (
              <div key={status} className="flex justify-between text-xs">
                <span className="capitalize text-text-secondary">{status}:</span>
                <span className={`font-mono ${colors[status] || 'text-text-secondary'}`}>
                  {count}
                </span>
              </div>
            )
          })}
          
          <hr className="border-border" />
          
          <div className="flex justify-between text-xs font-medium">
            <span className="text-text-primary">Total:</span>
            <span className="font-mono text-text-primary">{total}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function AddFeedForm({ onAdd, onCancel, error }) {
  const [newFeed, setNewFeed] = useState({ 
    url: '', 
    category: 'external_interview', 
    display_name: '', 
    tags: '' 
  })

  async function handleSubmit(e) {
    e.preventDefault()
    const body = {
      url: newFeed.url,
      category: newFeed.category,
      display_name: newFeed.display_name || null,
      tags: newFeed.tags ? newFeed.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
    }
    await onAdd(body)
    setNewFeed({ url: '', category: 'external_interview', display_name: '', tags: '' })
  }

  return (
    <form onSubmit={handleSubmit} className="border border-border rounded-lg p-4 mb-6 bg-surface">
      <div className="grid grid-cols-2 gap-3 mb-3">
        <input
          type="url" 
          required 
          placeholder="RSS/Atom feed URL"
          value={newFeed.url} 
          onChange={e => setNewFeed(p => ({...p, url: e.target.value}))}
          className="col-span-2 bg-gray-900 border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent"
        />
        <select
          value={newFeed.category} 
          onChange={e => setNewFeed(p => ({...p, category: e.target.value}))}
          className="bg-gray-900 border border-border rounded px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand-accent"
        >
          {CATEGORIES.map(c => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
        <input
          placeholder="Display name (optional)"
          value={newFeed.display_name} 
          onChange={e => setNewFeed(p => ({...p, display_name: e.target.value}))}
          className="bg-gray-900 border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent"
        />
        <input
          placeholder="Tags (comma-separated)"
          value={newFeed.tags} 
          onChange={e => setNewFeed(p => ({...p, tags: e.target.value}))}
          className="col-span-2 bg-gray-900 border border-border rounded px-3 py-2 text-sm text-text-primary placeholder-text-secondary focus:outline-none focus:border-brand-accent"
        />
      </div>
      
      {error && <p className="text-sm text-red-400 mb-2">{error}</p>}
      
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
          className="text-sm px-4 py-2 rounded bg-brand-accent text-white hover:bg-red-500 transition-colors"
        >
          Add Feed
        </button>
      </div>
    </form>
  )
}

export default function Sources() {
  const [feeds, setFeeds] = useState([])
  const [analysisQueue, setAnalysisQueue] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [addError, setAddError] = useState('')

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      const [feedsRes, queueRes] = await Promise.all([
        fetch('/api/feeds/'),
        fetch('/api/analysis/queue')
      ])
      
      if (feedsRes.ok) setFeeds(await feedsRes.json())
      if (queueRes.ok) setAnalysisQueue(await queueRes.json())
    } catch (e) {
      console.error('Failed to load data:', e)
    } finally {
      setLoading(false)
    }
  }

  async function addFeed(body) {
    setAddError('')
    try {
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
      await loadData()
    } catch (e) {
      setAddError(e.message)
    }
  }

  async function deleteFeed(id) {
    if (!confirm('Delete this feed and all its content?')) return
    await fetch(`/api/feeds/${id}`, { method: 'DELETE' })
    loadData()
  }

  async function pollFeed(id) {
    await fetch(`/api/feeds/${id}/poll`, { method: 'POST' })
    loadData()
  }

  async function pollAllFeeds() {
    await fetch('/api/feeds/poll', { method: 'POST' })
    loadData()
  }

  if (loading) return <div className="p-6 text-text-secondary">Loading sources...</div>

  return (
    <div className="p-6 max-w-6xl mx-auto overflow-y-auto h-full">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: Feeds */}
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-lg font-medium text-text-primary">RSS Feeds</h2>
              <p className="text-sm text-text-secondary">{feeds.length} feed{feeds.length !== 1 ? 's' : ''}</p>
            </div>
            <div className="flex gap-2">
              <button 
                onClick={pollAllFeeds}
                className="text-sm px-3 py-2 rounded bg-gray-800 text-text-secondary hover:bg-gray-700 transition-colors"
              >
                Poll All
              </button>
              <button 
                onClick={() => setShowAdd(!showAdd)}
                className="text-sm px-3 py-2 rounded bg-brand-accent text-white hover:bg-red-500 transition-colors"
              >
                + Add Feed
              </button>
            </div>
          </div>

          {showAdd && (
            <AddFeedForm 
              onAdd={addFeed} 
              onCancel={() => setShowAdd(false)} 
              error={addError} 
            />
          )}

          <div className="space-y-3 mb-8">
            {feeds.length === 0 ? (
              <p className="text-text-secondary text-sm">
                No feeds configured. Add your first RSS feed above.
              </p>
            ) : (
              feeds.map(f => (
                <FeedCard 
                  key={f.feed_id} 
                  feed={f} 
                  onDelete={deleteFeed} 
                  onPoll={pollFeed} 
                />
              ))
            )}
          </div>

          {/* PDF Upload Section */}
          <div className="border-t border-border pt-6">
            <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wider mb-3">
              PDF Upload
            </h3>
            <PDFUploader onUploaded={loadData} />
          </div>
        </div>

        {/* Right column: Ingest status */}
        <div>
          <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wider mb-3">
            Ingest Activity
          </h3>
          <IngestStatus analysisQueue={analysisQueue} />
        </div>
      </div>
    </div>
  )
}