import React, { useState, useEffect } from 'react'

function FrameworkCard({ fw, rank }) {
  const alignColors = {
    agree: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
    partial: 'bg-amber-900/40 text-amber-300 border-amber-800',
    diverge: 'bg-red-900/40 text-red-300 border-red-800',
  }
  const acls = alignColors[fw.thesis_alignment] || 'bg-gray-800 text-gray-400 border-gray-700'

  return (
    <div className="border border-gray-800 rounded-lg p-4 bg-gray-900/30">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-brand-accent font-semibold text-sm">#{rank}</span>
          <h4 className="text-sm font-medium text-white">{fw.framework_name}</h4>
        </div>
        <div className="flex items-center gap-2">
          {fw.thesis_alignment && fw.thesis_alignment !== 'unrelated' && (
            <span className={`text-xs px-2 py-0.5 rounded border ${acls}`}>
              {fw.thesis_alignment}
            </span>
          )}
          <span className="text-xs text-gray-500">{fw.guest_name}</span>
        </div>
      </div>
      {/* Score bar */}
      <div className="w-full h-1.5 bg-gray-800 rounded-full mb-2">
        <div className="h-1.5 bg-brand-accent rounded-full transition-all"
          style={{ width: `${(fw.composite_score || 0) * 100}%` }} />
      </div>
      <p className="text-xs text-gray-400 mb-1">{fw.ranking_rationale}</p>
      {fw.key_insight && (
        <p className="text-xs text-gray-300"><span className="text-brand-accent">Insight:</span> {fw.key_insight}</p>
      )}
    </div>
  )
}

function MetricCard({ label, value, color }) {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-3 text-center">
      <div className={`text-2xl font-semibold ${color || 'text-white'}`}>{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  )
}

export default function Briefings() {
  const [briefing, setBriefing] = useState(null)
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => { loadLatest() }, [])

  async function loadLatest() {
    setLoading(true)
    setError(null)
    try {
      const listRes = await fetch('/api/chat/briefings')
      setList(await listRes.json())

      const res = await fetch('/api/chat/briefings/latest')
      if (res.ok) {
        setBriefing(await res.json())
      } else if (res.status === 404) {
        setBriefing(null)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="p-6 text-gray-400">Loading briefings...</div>

  if (!briefing) {
    return (
      <div className="p-6 max-w-3xl mx-auto text-center">
        <div className="w-16 h-16 rounded-xl bg-gray-800 flex items-center justify-center mx-auto mb-4">
          <span className="text-3xl">📋</span>
        </div>
        <h2 className="text-lg font-medium text-white mb-2">No Briefings Yet</h2>
        <p className="text-gray-400 text-sm">
          The first weekly briefing will be generated after content has been
          ingested and analyzed. The synthesis runs every Sunday at 6 AM UTC.
        </p>
      </div>
    )
  }

  const scorecard = briefing.thesis_scorecard?.thesis || {}
  const accuracy = scorecard.accuracy_rate
  const frameworks = briefing.top_frameworks || []
  const blindSpots = briefing.blind_spot_alerts?.recent_mutual || []
  const narratives = briefing.narrative_shifts || {}

  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-lg font-medium text-white">Weekly Intelligence Briefing</h2>
        <p className="text-sm text-gray-400">
          {briefing.week_start && new Date(briefing.week_start).toLocaleDateString()} —{' '}
          {briefing.week_end && new Date(briefing.week_end).toLocaleDateString()}
        </p>
      </div>

      {/* Scorecard metrics */}
      <div className="grid grid-cols-4 gap-3 mb-8">
        <MetricCard label="Accuracy" value={accuracy != null ? `${(accuracy * 100).toFixed(0)}%` : 'N/A'} color="text-blue-400" />
        <MetricCard label="Validated" value={scorecard.validated || 0} color="text-emerald-400" />
        <MetricCard label="Invalidated" value={scorecard.invalidated || 0} color="text-red-400" />
        <MetricCard label="Total Tracked" value={scorecard.total || 0} />
      </div>

      {/* Top 5 Frameworks */}
      <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3">Top 5 frameworks</h3>
      <div className="grid gap-3 mb-8">
        {frameworks.length > 0 ? (
          frameworks.map((fw, i) => <FrameworkCard key={i} fw={fw} rank={i + 1} />)
        ) : (
          <p className="text-sm text-gray-500">No frameworks ranked yet.</p>
        )}
      </div>

      {/* Blind Spot Alerts */}
      <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3">Blind spot alerts</h3>
      <div className="grid gap-2 mb-8">
        {blindSpots.length > 0 ? (
          blindSpots.map((spot, i) => {
            const sevColor = { high: 'border-red-700 bg-red-950/20', medium: 'border-amber-800 bg-amber-950/20', low: 'border-gray-700' }
            return (
              <div key={i} className={`border-l-2 rounded-r-lg px-4 py-3 ${sevColor[spot.severity] || sevColor.low}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-xs font-medium uppercase ${spot.severity === 'high' ? 'text-red-400' : spot.severity === 'medium' ? 'text-amber-400' : 'text-gray-400'}`}>
                    {spot.severity}
                  </span>
                  <span className="text-sm text-white font-medium">{spot.topic}</span>
                </div>
                <p className="text-xs text-gray-400">{spot.description}</p>
              </div>
            )
          })
        ) : (
          <p className="text-sm text-gray-500">No blind spots detected this week.</p>
        )}
      </div>

      {/* Narrative shifts */}
      <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3">Narrative shifts</h3>
      {['strengthening', 'weakening', 'pivoting'].map(dir => {
        const items = narratives[dir] || []
        if (items.length === 0) return null
        const label = { strengthening: 'Strengthening', weakening: 'Weakening', pivoting: 'Pivoting' }
        const color = { strengthening: 'text-emerald-400', weakening: 'text-red-400', pivoting: 'text-amber-400' }
        return (
          <div key={dir} className="mb-4">
            <h4 className={`text-xs font-medium ${color[dir]} mb-1`}>{label[dir]}</h4>
            {items.map((it, i) => (
              <p key={i} className="text-xs text-gray-400 mb-1">
                <span className="text-gray-300">{it.thread}:</span> {it.latest}
              </p>
            ))}
          </div>
        )
      })}

      {/* Previous briefings */}
      {list.length > 1 && (
        <>
          <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3 mt-8">Previous briefings</h3>
          <div className="grid gap-2">
            {list.slice(1).map(b => (
              <div key={b.briefing_id} className="text-xs text-gray-500 border border-gray-800 rounded px-3 py-2 flex justify-between">
                <span>{new Date(b.week_start).toLocaleDateString()} — {new Date(b.week_end).toLocaleDateString()}</span>
                <span>{b.items_ingested} ingested, {b.items_analyzed} analyzed</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
