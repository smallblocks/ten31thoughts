import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

function ReviewCard({ count, description, to, loading = false }) {
  return (
    <Link 
      to={to}
      className="block border border-border rounded-lg p-3 bg-surface hover:bg-gray-800 transition-colors"
    >
      <div className="text-2xl font-mono text-text-primary mb-1">
        {loading ? '–' : count}
      </div>
      <div className="text-sm text-text-secondary">{description}</div>
    </Link>
  )
}

function DigestSection({ digest }) {
  const [expanded, setExpanded] = useState(false)

  if (!digest) {
    return (
      <div className="border border-border rounded-lg p-6 bg-surface">
        <h2 className="text-lg font-medium text-text-primary mb-2">No digest yet</h2>
        <p className="text-sm text-text-secondary">
          First digest runs after content has been ingested and analyzed.
        </p>
      </div>
    )
  }

  // Use opening field if available, fall back to HTML parsing
  let pullQuote = null
  if (digest.opening) {
    pullQuote = digest.opening
  } else if (digest.html_content) {
    const match = digest.html_content.match(/<p[^>]*>(.*?)<\/p>/i)
    if (match) {
      const firstPara = match[1].replace(/<[^>]*>/g, '') // Strip HTML tags
      if (firstPara.length > 50) {
        pullQuote = firstPara
      }
    }
  }

  return (
    <div className="space-y-6">
      {/* Digest header */}
      <div className="border border-border rounded-lg p-6 bg-surface">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-lg font-medium text-text-primary mb-1">Weekly Digest</h2>
            <p className="text-sm text-text-secondary">
              {new Date(digest.period_start).toLocaleDateString()} — {new Date(digest.period_end).toLocaleDateString()}
            </p>
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm text-brand-accent hover:text-red-400 transition-colors"
          >
            Read full digest →
          </button>
        </div>
        
        {pullQuote && (
          <blockquote className="font-serif text-base text-text-primary leading-relaxed italic border-l-2 border-brand-accent pl-4">
            "{pullQuote}"
          </blockquote>
        )}
      </div>

      {/* Full digest content */}
      {expanded && digest.html_content && (
        <div className="border border-border rounded-lg p-6 bg-surface">
          <div
            className="digest-content text-text-primary"
            dangerouslySetInnerHTML={{ __html: digest.html_content }}
          />
        </div>
      )}
    </div>
  )
}

function PreviousDigests({ digests }) {
  const [openIds, setOpenIds] = useState({})

  if (digests.length === 0) return null

  function toggle(id) {
    setOpenIds(prev => ({ ...prev, [id]: !prev[id] }))
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wider">
        Previous Digests
      </h3>
      <div className="space-y-2">
        {digests.map(digest => (
          <div key={digest.digest_id} className="border border-border rounded-lg bg-surface overflow-hidden">
            <button
              onClick={() => toggle(digest.digest_id)}
              className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-gray-800 transition-colors"
            >
              <span className="text-sm text-text-secondary">
                {new Date(digest.period_start).toLocaleDateString()} — {new Date(digest.period_end).toLocaleDateString()}
              </span>
              <span className="text-xs text-text-secondary">
                {openIds[digest.digest_id] ? '▼' : '▶'}
              </span>
            </button>
            {openIds[digest.digest_id] && digest.html_content && (
              <div className="px-4 pb-4 border-t border-border">
                <div
                  className="digest-content text-text-primary mt-3"
                  dangerouslySetInnerHTML={{ __html: digest.html_content }}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ThisWeek() {
  const [digest, setDigest] = useState(null)
  const [previousDigests, setPreviousDigests] = useState([])
  const [connectionsCount, setConnectionsCount] = useState(0)
  const [signalsCount, setSignalsCount] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    try {
      // Load latest digest
      const digestRes = await fetch('/api/digest/latest')
      if (digestRes.ok) {
        setDigest(await digestRes.json())
      }

      // Load previous digests
      const digestListRes = await fetch('/api/digest/?limit=20')
      if (digestListRes.ok) {
        const data = await digestListRes.json()
        const allDigests = data.digests || []
        setPreviousDigests(allDigests.slice(1)) // Skip first one (latest)
      }

      // Load unrated connections count
      const connectionsRes = await fetch('/api/connections/?unrated=true&limit=1')
      if (connectionsRes.ok) {
        const connections = await connectionsRes.json()
        setConnectionsCount(connections.length)
      }

      // Load signals count
      const signalsRes = await fetch('/api/signals/?limit=100')
      if (signalsRes.ok) {
        const signals = await signalsRes.json()
        setSignalsCount(signals.length)
      }
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full space-y-8">
      {/* Latest digest */}
      <DigestSection digest={digest} />

      {/* Review queue */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wider">
          Review Queue
        </h3>
        <div className="grid grid-cols-3 gap-4">
          <ReviewCard 
            count={connectionsCount}
            description="connections pending review"
            to="/connections?unrated=true"
            loading={loading}
          />
          <ReviewCard 
            count={signalsCount}
            description="signals to triage"
            to="/connections/signals"
            loading={loading}
          />
          <ReviewCard 
            count="—"
            description="notes resurfaced this week"
            to="/notes"
            loading={loading}
          />
        </div>
      </div>

      {/* Previous digests */}
      <PreviousDigests digests={previousDigests} />
    </div>
  )
}