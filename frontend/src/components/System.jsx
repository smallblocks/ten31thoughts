import React, { useState, useEffect } from 'react'

export default function System() {
  const [status, setStatus] = useState(null)
  const [queue, setQueue] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadStatus() }, [])

  async function loadStatus() {
    setLoading(true)
    try {
      const [statusRes, queueRes] = await Promise.all([
        fetch('/api/status'),
        fetch('/api/analysis/queue'),
      ])
      if (statusRes.ok) setStatus(await statusRes.json())
      if (queueRes.ok) setQueue(await queueRes.json())
    } catch (e) {
      console.error('Failed to load status:', e)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="p-6 text-text-secondary">Loading system status...</div>

  const content = status?.content || {}

  return (
    <div className="p-6 max-w-3xl mx-auto overflow-y-auto h-full">
      <h2 className="text-lg font-medium text-text-primary mb-6">System</h2>

      {/* Health */}
      <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
        <div className="flex items-center gap-3 mb-4">
          <div className={`w-2.5 h-2.5 rounded-full ${
            status?.status === 'healthy' ? 'bg-emerald-500' : 'bg-red-500'
          }`} />
          <span className="text-sm text-text-primary">
            {status?.status === 'healthy' ? 'Healthy' : 'Error'}
          </span>
          <span className="text-xs font-mono text-text-secondary">v{status?.version}</span>
        </div>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-xl font-mono text-text-primary">{content.feeds_active || 0}</div>
            <div className="text-xs text-text-secondary">Active Feeds</div>
          </div>
          <div>
            <div className="text-xl font-mono text-text-primary">{content.total_items || 0}</div>
            <div className="text-xs text-text-secondary">Total Items</div>
          </div>
          <div>
            <div className="text-xl font-mono text-text-primary">{content.feeds_total || 0}</div>
            <div className="text-xs text-text-secondary">Total Feeds</div>
          </div>
        </div>
      </div>

      {/* Analysis Queue */}
      {queue && (
        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wider mb-3">
            Analysis Queue
          </h3>
          <div className="grid grid-cols-4 gap-3 text-center">
            <div>
              <div className="text-lg font-mono text-amber-400">{queue.total_pending}</div>
              <div className="text-xs text-text-secondary">Pending</div>
            </div>
            <div>
              <div className="text-lg font-mono text-blue-400">{queue.total_analyzing}</div>
              <div className="text-xs text-text-secondary">Analyzing</div>
            </div>
            <div>
              <div className="text-lg font-mono text-emerald-400">{queue.total_complete}</div>
              <div className="text-xs text-text-secondary">Complete</div>
            </div>
            <div>
              <div className="text-lg font-mono text-red-400">{queue.total_error}</div>
              <div className="text-xs text-text-secondary">Errors</div>
            </div>
          </div>
          <hr className="border-border mt-3 mb-2" />
          <div className="flex gap-6 text-xs text-text-secondary">
            <span>Thesis pending: <span className="font-mono">{queue.our_thesis_pending}</span></span>
            <span>External pending: <span className="font-mono">{queue.external_pending}</span></span>
          </div>
        </div>
      )}

      {/* Content by status */}
      {content.by_status && (
        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wider mb-3">
            Content by Status
          </h3>
          <div className="space-y-2">
            {Object.entries(content.by_status).map(([s, count]) => (
              <div key={s} className="flex items-center gap-3">
                <span className="text-xs text-text-secondary w-24">{s}</span>
                <div className="flex-1 h-2 bg-gray-800 rounded-full">
                  <div
                    className="h-2 bg-brand-accent rounded-full"
                    style={{ width: `${content.total_items ? (count / content.total_items) * 100 : 0}%` }}
                  />
                </div>
                <span className="text-xs font-mono text-text-secondary w-8 text-right">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Content by category */}
      {content.by_category && (
        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wider mb-3">
            Content by Category
          </h3>
          <div className="grid grid-cols-2 gap-4 text-center">
            <div>
              <div className="text-lg font-mono text-amber-400">{content.by_category.our_thesis || 0}</div>
              <div className="text-xs text-text-secondary">Our Thesis</div>
            </div>
            <div>
              <div className="text-lg font-mono text-blue-400">{content.by_category.external_interview || 0}</div>
              <div className="text-xs text-text-secondary">External Interviews</div>
            </div>
          </div>
        </div>
      )}

      <div className="text-center">
        <button
          onClick={loadStatus}
          className="text-sm text-text-secondary hover:text-text-primary transition-colors"
        >
          Refresh
        </button>
      </div>
    </div>
  )
}
