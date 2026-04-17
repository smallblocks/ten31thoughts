import React, { useState, useEffect } from 'react'

function DigestAccordion({ digest, isOpen, onToggle }) {
  return (
    <div className="border border-gray-800 rounded-lg bg-gray-900/20 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-gray-900/40 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">
            {digest.period_start && new Date(digest.period_start).toLocaleDateString()} —{' '}
            {digest.period_end && new Date(digest.period_end).toLocaleDateString()}
          </span>
        </div>
        <span className="text-xs text-gray-500">{isOpen ? '▼' : '▶'}</span>
      </button>
      {isOpen && digest.html_content && (
        <div className="px-4 pb-4 border-t border-gray-800">
          <div
            className="prose prose-invert prose-sm max-w-none text-gray-200 leading-relaxed mt-3"
            dangerouslySetInnerHTML={{ __html: digest.html_content }}
          />
        </div>
      )}
    </div>
  )
}

export default function Digest() {
  const [latest, setLatest] = useState(null)
  const [previous, setPrevious] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [openIds, setOpenIds] = useState({})

  useEffect(() => { loadDigests() }, [])

  async function loadDigests() {
    setLoading(true)
    setError(null)
    try {
      // Try to get latest
      const latestRes = await fetch('/api/digest/latest')
      if (latestRes.ok) {
        setLatest(await latestRes.json())
      } else if (latestRes.status === 404) {
        setLatest(null)
      }

      // Get list for previous digests
      const listRes = await fetch('/api/digest/?limit=20')
      if (listRes.ok) {
        const data = await listRes.json()
        const digests = data.digests || []
        // Skip the first one since it's the latest
        setPrevious(digests.length > 1 ? digests.slice(1) : [])
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function toggleAccordion(id) {
    setOpenIds(prev => ({ ...prev, [id]: !prev[id] }))
  }

  if (loading) return <div className="p-6 text-gray-400">Loading digests...</div>
  if (error) return <div className="p-6 text-red-400">Error: {error}</div>

  if (!latest) {
    return (
      <div className="p-6 max-w-3xl mx-auto text-center">
        <div className="w-16 h-16 rounded-xl bg-gray-800 flex items-center justify-center mx-auto mb-4">
          <span className="text-3xl">📰</span>
        </div>
        <h2 className="text-lg font-medium text-white mb-2">No Digests Yet</h2>
        <p className="text-gray-400 text-sm">
          The first weekly digest will be generated after content has been
          ingested and analyzed. Digests run automatically on schedule.
        </p>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
      {/* Latest digest header */}
      <div className="mb-6">
        <h2 className="text-lg font-medium text-white">Weekly Digest</h2>
        <p className="text-sm text-gray-400">
          {latest.period_start && new Date(latest.period_start).toLocaleDateString()} —{' '}
          {latest.period_end && new Date(latest.period_end).toLocaleDateString()}
        </p>
      </div>

      {/* Latest digest content */}
      {latest.html_content ? (
        <div className="border border-gray-800 rounded-lg p-6 bg-gray-900/30 mb-8">
          <div
            className="prose prose-invert prose-sm max-w-none text-gray-200 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: latest.html_content }}
          />
        </div>
      ) : (
        <div className="border border-gray-800 rounded-lg p-6 bg-gray-900/30 mb-8">
          <p className="text-sm text-gray-400">Digest content is empty.</p>
        </div>
      )}

      {/* Previous digests */}
      {previous.length > 0 && (
        <>
          <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3">
            Previous Digests
          </h3>
          <div className="space-y-2">
            {previous.map(d => (
              <DigestAccordion
                key={d.digest_id}
                digest={d}
                isOpen={!!openIds[d.digest_id]}
                onToggle={() => toggleAccordion(d.digest_id)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
