import React, { useState, useEffect } from 'react'

export default function Status() {
  const [status, setStatus] = useState(null)
  const [queue, setQueue] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadStatus() }, [])

  async function loadStatus() {
    try {
      const [statusRes, queueRes] = await Promise.all([
        fetch('/api/status'),
        fetch('/api/analysis/queue'),
      ])
      setStatus(await statusRes.json())
      setQueue(await queueRes.json())
    } catch (e) {
      console.error('Failed to load status:', e)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="p-6 text-gray-400">Loading status...</div>

  const content = status?.content || {}

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h2 className="text-lg font-medium text-white mb-6">System Status</h2>

      {/* Health */}
      <div className="border border-gray-800 rounded-lg p-4 mb-6 bg-gray-900/30">
        <div className="flex items-center gap-3 mb-3">
          <div className={`w-3 h-3 rounded-full ${status?.status === 'healthy' ? 'bg-emerald-500' : 'bg-red-500'}`} />
          <span className="text-sm font-medium text-white">
            {status?.status === 'healthy' ? 'Service Healthy' : 'Service Error'}
          </span>
          <span className="text-xs text-gray-500">v{status?.version}</span>
        </div>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-xl font-semibold text-white">{content.feeds_active || 0}</div>
            <div className="text-xs text-gray-500">Active Feeds</div>
          </div>
          <div>
            <div className="text-xl font-semibold text-white">{content.total_items || 0}</div>
            <div className="text-xs text-gray-500">Total Items</div>
          </div>
          <div>
            <div className="text-xl font-semibold text-white">{content.feeds_total || 0}</div>
            <div className="text-xs text-gray-500">Total Feeds</div>
          </div>
        </div>
      </div>

      {/* Analysis Queue */}
      {queue && (
        <div className="border border-gray-800 rounded-lg p-4 mb-6 bg-gray-900/30">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Analysis Queue</h3>
          <div className="grid grid-cols-4 gap-3 text-center">
            <div>
              <div className="text-lg font-semibold text-amber-400">{queue.total_pending}</div>
              <div className="text-xs text-gray-500">Pending</div>
            </div>
            <div>
              <div className="text-lg font-semibold text-blue-400">{queue.total_analyzing}</div>
              <div className="text-xs text-gray-500">Analyzing</div>
            </div>
            <div>
              <div className="text-lg font-semibold text-emerald-400">{queue.total_complete}</div>
              <div className="text-xs text-gray-500">Complete</div>
            </div>
            <div>
              <div className="text-lg font-semibold text-red-400">{queue.total_error}</div>
              <div className="text-xs text-gray-500">Errors</div>
            </div>
          </div>
          <div className="mt-3 pt-3 border-t border-gray-800 flex gap-6 text-xs text-gray-400">
            <span>Thesis pending: {queue.our_thesis_pending}</span>
            <span>External pending: {queue.external_pending}</span>
          </div>
        </div>
      )}

      {/* Content by status */}
      {content.by_status && (
        <div className="border border-gray-800 rounded-lg p-4 mb-6 bg-gray-900/30">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Content by Status</h3>
          <div className="space-y-2">
            {Object.entries(content.by_status).map(([status, count]) => (
              <div key={status} className="flex items-center gap-3">
                <span className="text-xs text-gray-400 w-24">{status}</span>
                <div className="flex-1 h-2 bg-gray-800 rounded-full">
                  <div className="h-2 bg-brand-accent rounded-full" style={{
                    width: `${content.total_items ? (count / content.total_items) * 100 : 0}%`
                  }} />
                </div>
                <span className="text-xs text-gray-400 w-8 text-right">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Content by category */}
      {content.by_category && (
        <div className="border border-gray-800 rounded-lg p-4 bg-gray-900/30">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Content by Category</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="text-center">
              <div className="text-lg font-semibold text-amber-400">{content.by_category.our_thesis || 0}</div>
              <div className="text-xs text-gray-500">Our Thesis</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-semibold text-blue-400">{content.by_category.external_interview || 0}</div>
              <div className="text-xs text-gray-500">External Interviews</div>
            </div>
          </div>
        </div>
      )}

      <div className="mt-6 text-center">
        <button onClick={loadStatus}
          className="text-sm text-gray-400 hover:text-white transition-colors">
          Refresh Status
        </button>
      </div>
    </div>
  )
}
