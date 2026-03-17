import React, { useState, useEffect, useMemo } from 'react'

function GradeChip({ grade }) {
  if (!grade) return null
  const colors = {
    'A': 'bg-emerald-900/50 text-emerald-300 border-emerald-700',
    'A-': 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
    'B+': 'bg-blue-900/40 text-blue-300 border-blue-800',
    'B': 'bg-blue-900/30 text-blue-300 border-blue-800',
    'B-': 'bg-blue-900/20 text-blue-400 border-blue-900',
    'C+': 'bg-amber-900/30 text-amber-300 border-amber-800',
    'C': 'bg-amber-900/20 text-amber-400 border-amber-900',
    'D': 'bg-red-900/30 text-red-300 border-red-800',
    'F': 'bg-red-900/50 text-red-200 border-red-700',
  }
  return (
    <span className={`inline-block text-xs font-mono font-bold px-2 py-0.5 rounded border ${colors[grade] || 'bg-gray-800 text-gray-400 border-gray-700'}`}>
      {grade}
    </span>
  )
}

function AlignmentChip({ alignment }) {
  const colors = {
    agree: 'bg-emerald-900/40 text-emerald-300',
    partial: 'bg-amber-900/40 text-amber-300',
    diverge: 'bg-red-900/40 text-red-300',
    unrelated: 'bg-gray-800 text-gray-500',
  }
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${colors[alignment] || colors.unrelated}`}>
      {alignment}
    </span>
  )
}

function TrendArrow({ trend }) {
  if (trend === 'improving') return <span className="text-emerald-400 text-xs">↑ improving</span>
  if (trend === 'declining') return <span className="text-red-400 text-xs">↓ declining</span>
  return <span className="text-gray-500 text-xs">— stable</span>
}

function ScoreBar({ score, small }) {
  if (score == null) return <span className="text-xs text-gray-600">—</span>
  const pct = Math.round(score * 100)
  const h = small ? 'h-1' : 'h-1.5'
  return (
    <div className="flex items-center gap-2">
      <div className={`flex-1 ${h} bg-gray-800 rounded-full`}>
        <div className={`${h} bg-brand-accent rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 font-mono w-8 text-right">{pct}%</span>
    </div>
  )
}

function SocialLinks({ x_handle, linkedin_url, website_url }) {
  if (!x_handle && !linkedin_url && !website_url) return null
  return (
    <div className="flex items-center gap-2">
      {x_handle && (
        <a href={`https://x.com/${x_handle}`} target="_blank" rel="noopener noreferrer"
          className="text-xs text-gray-500 hover:text-white transition-colors" title={`@${x_handle}`}>
          𝕏
        </a>
      )}
      {linkedin_url && (
        <a href={linkedin_url} target="_blank" rel="noopener noreferrer"
          className="text-xs text-gray-500 hover:text-blue-400 transition-colors" title="LinkedIn">
          in
        </a>
      )}
      {website_url && (
        <a href={website_url} target="_blank" rel="noopener noreferrer"
          className="text-xs text-gray-500 hover:text-brand-accent transition-colors" title="Website">
          🔗
        </a>
      )}
    </div>
  )
}

function ELOBadge({ rating, count }) {
  if (!rating || !count) return null
  const r = Math.round(rating)
  let color = 'text-gray-400 border-gray-700'
  if (r >= 1700) color = 'text-amber-300 border-amber-600 bg-amber-950/30'
  else if (r >= 1550) color = 'text-emerald-300 border-emerald-700 bg-emerald-950/20'
  else if (r >= 1450) color = 'text-gray-300 border-gray-600'
  else if (r >= 1300) color = 'text-orange-300 border-orange-700 bg-orange-950/20'
  else color = 'text-red-300 border-red-700 bg-red-950/20'

  return (
    <span className={`inline-flex items-center gap-1 text-xs font-mono px-2 py-0.5 rounded border ${color}`}
      title={`ELO rating based on ${count} market-resolved prediction${count !== 1 ? 's' : ''}`}>
      ⚡ {r}
    </span>
  )
}

function PredictionReceipt({ pred }) {
  const statusColors = {
    validated: 'text-emerald-400', invalidated: 'text-red-400',
    partially_validated: 'text-amber-400', pending: 'text-gray-400', expired: 'text-gray-600',
  }
  const statusIcon = {
    validated: '✓', invalidated: '✗', partially_validated: '~', pending: '○', expired: '—',
  }

  return (
    <div className="border border-gray-800 rounded-lg p-3 bg-gray-900/20">
      <div className="flex items-start justify-between gap-3 mb-2">
        <p className="text-sm text-gray-200 flex-1">{pred.prediction || pred.claim}</p>
        <span className={`text-sm font-mono font-bold shrink-0 ${statusColors[pred.status] || 'text-gray-500'}`}>
          {statusIcon[pred.status] || '?'} {(pred.status || 'pending').toUpperCase()}
        </span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
        {pred.episode && <span>Episode: <span className="text-gray-300">{pred.episode}</span></span>}
        {pred.date && <span>Called: <span className="text-gray-300">{new Date(pred.date).toLocaleDateString()}</span></span>}
      </div>
      {pred.market_title && (
        <div className="mt-2 border-t border-gray-800 pt-2 flex items-center justify-between text-xs">
          <a href={pred.market_url} target="_blank" rel="noopener noreferrer"
            className="text-brand-accent hover:underline">{pred.market_title}</a>
          <span className="text-gray-500">
            {pred.platform && <span className="uppercase mr-2">{pred.platform}</span>}
            {pred.market_result ? (
              <span className={pred.correct ? 'text-emerald-400' : 'text-red-400'}>
                Resolved: {pred.market_result.toUpperCase()}
              </span>
            ) : pred.market_probability != null ? (
              <span>Market: {Math.round(pred.market_probability * 100)}%</span>
            ) : null}
          </span>
        </div>
      )}
    </div>
  )
}

const SORT_OPTIONS = [
  { id: 'score_desc', label: 'Score ↓', fn: (a, b) => (b.avg_first_principles_score || 0) - (a.avg_first_principles_score || 0) },
  { id: 'score_asc', label: 'Score ↑', fn: (a, b) => (a.avg_first_principles_score || 0) - (b.avg_first_principles_score || 0) },
  { id: 'elo_desc', label: 'ELO ↓', fn: (a, b) => (b.elo_rating || 1500) - (a.elo_rating || 1500) },
  { id: 'elo_asc', label: 'ELO ↑', fn: (a, b) => (a.elo_rating || 1500) - (b.elo_rating || 1500) },
  { id: 'appearances', label: 'Appearances', fn: (a, b) => b.appearances - a.appearances },
  { id: 'consistency', label: 'Consistency', fn: (a, b) => (a.consistency || 1) - (b.consistency || 1) },
  { id: 'name', label: 'Name A-Z', fn: (a, b) => a.guest_name.localeCompare(b.guest_name) },
]

export default function Scorecards() {
  const [guests, setGuests] = useState([])
  const [selected, setSelected] = useState(null)
  const [scorecard, setScorecard] = useState(null)
  const [marketLinks, setMarketLinks] = useState([])
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)

  // Filters
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('score_desc')

  useEffect(() => { loadGuests() }, [])

  async function loadGuests() {
    setLoading(true)
    try {
      const res = await fetch('/api/episodes/guests?min_appearances=1')
      if (res.ok) setGuests(await res.json())
    } catch (e) {
      console.error('Failed to load guests:', e)
    } finally {
      setLoading(false)
    }
  }

  async function loadScorecard(name) {
    setSelected(name)
    setDetailLoading(true)
    setScorecard(null)
    setMarketLinks([])
    try {
      const [scRes, mkRes] = await Promise.all([
        fetch(`/api/episodes/guests/${encodeURIComponent(name)}/scorecard`),
        fetch(`/api/markets/links?limit=100`),
      ])
      if (scRes.ok) setScorecard(await scRes.json())
      if (mkRes.ok) {
        const allLinks = await mkRes.json()
        setMarketLinks(allLinks.filter(l => l.prediction))
      }
    } catch (e) {
      console.error('Failed to load scorecard:', e)
    } finally {
      setDetailLoading(false)
    }
  }

  // Filtered + sorted guests
  const filteredGuests = useMemo(() => {
    let list = guests
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(g =>
        g.guest_name.toLowerCase().includes(q) ||
        (g.bio || '').toLowerCase().includes(q) ||
        (g.x_handle || '').toLowerCase().includes(q)
      )
    }
    const sortOpt = SORT_OPTIONS.find(s => s.id === sortBy)
    if (sortOpt) list = [...list].sort(sortOpt.fn)
    return list
  }, [guests, search, sortBy])

  if (loading) return <div className="p-6 text-gray-400">Loading scorecards...</div>

  // ─── Guest detail view ───
  if (selected && scorecard) {
    return (
      <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
        <button onClick={() => { setSelected(null); setScorecard(null) }}
          className="text-sm text-gray-400 hover:text-white mb-4 flex items-center gap-1">
          ← All Guests
        </button>

        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold text-white">
                {scorecard.display_name || scorecard.guest_name}
              </h2>
              <SocialLinks
                x_handle={scorecard.x_handle}
                linkedin_url={scorecard.linkedin_url}
                website_url={scorecard.website_url}
              />
            </div>
            {scorecard.bio && (
              <p className="text-sm text-gray-400 mt-0.5">{scorecard.bio}</p>
            )}
            <p className="text-sm text-gray-500 mt-1">
              {scorecard.total_appearances} appearances · {scorecard.total_frameworks} frameworks
            </p>
          </div>
          <div className="text-right">
            <div className="flex items-center gap-2 justify-end">
              <GradeChip grade={scorecard.reasoning_grade} />
              <ELOBadge rating={scorecard.elo_rating} count={scorecard.elo_predictions_counted} />
              <TrendArrow trend={scorecard.trend} />
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Avg: {scorecard.avg_first_principles_score != null ? (scorecard.avg_first_principles_score * 100).toFixed(0) + '%' : 'N/A'}
              {scorecard.best_score != null && <> · Best: {(scorecard.best_score * 100).toFixed(0)}%</>}
              {scorecard.worst_score != null && <> · Worst: {(scorecard.worst_score * 100).toFixed(0)}%</>}
            </p>
          </div>
        </div>

        {/* Thesis alignment */}
        {scorecard.thesis_alignment_distribution && (
          <div className="grid grid-cols-4 gap-2 mb-6">
            {Object.entries(scorecard.thesis_alignment_distribution).map(([key, val]) => (
              <div key={key} className="bg-gray-900/50 border border-gray-800 rounded-lg p-2 text-center">
                <div className="text-lg font-semibold text-white">{val}</div>
                <div className="text-xs text-gray-500">{key}</div>
              </div>
            ))}
          </div>
        )}

        {/* Domain strengths/weaknesses */}
        {(scorecard.strongest_domains?.length > 0 || scorecard.weakest_domains?.length > 0) && (
          <div className="grid grid-cols-2 gap-4 mb-6">
            {scorecard.strongest_domains?.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-emerald-400 uppercase tracking-wider mb-2">Strongest Domains</h4>
                {scorecard.strongest_domains.map((d, i) => (
                  <div key={i} className="flex items-center justify-between text-xs py-1">
                    <span className="text-gray-300">{d.title}</span>
                    <span className="text-emerald-400 font-mono">{(d.avg_score * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            )}
            {scorecard.weakest_domains?.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-red-400 uppercase tracking-wider mb-2">Weakest Domains</h4>
                {scorecard.weakest_domains.map((d, i) => (
                  <div key={i} className="flex items-center justify-between text-xs py-1">
                    <span className="text-gray-300">{d.title}</span>
                    <span className="text-red-400 font-mono">{(d.avg_score * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Appearances timeline */}
        <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3">Appearances</h3>
        <div className="space-y-2 mb-8">
          {(scorecard.score_trend || []).map((entry, i) => (
            <div key={i} className="border border-gray-800 rounded-lg p-3 bg-gray-900/20 hover:bg-gray-900/40 transition-colors">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <GradeChip grade={entry.reasoning_grade} />
                  <span className="text-sm text-white">{entry.framework}</span>
                </div>
                <AlignmentChip alignment={entry.thesis_alignment} />
              </div>
              <div className="flex items-center justify-between">
                <a href={entry.url} target="_blank" rel="noopener noreferrer"
                  className="text-xs text-gray-400 hover:text-brand-accent truncate max-w-md">
                  {entry.episode}
                </a>
                <span className="text-xs text-gray-600">
                  {entry.date ? new Date(entry.date).toLocaleDateString() : ''}
                </span>
              </div>
              {entry.first_principles_score != null && (
                <div className="mt-2"><ScoreBar score={entry.first_principles_score} small /></div>
              )}
            </div>
          ))}
        </div>

        {/* Predictions with receipts */}
        {(scorecard.predictions?.length > 0 || marketLinks.length > 0) && (
          <>
            <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3">Predictions & Receipts</h3>
            <div className="space-y-2 mb-8">
              {marketLinks.map((ml, i) => (
                <PredictionReceipt key={`ml-${i}`} pred={{
                  prediction: ml.prediction, market_title: ml.market_title,
                  market_url: ml.market_url, platform: ml.platform,
                  market_result: ml.market_result, market_probability: ml.current_price,
                  correct: ml.market_result === ml.our_side,
                  status: ml.market_result ? (ml.market_result === ml.our_side ? 'validated' : 'invalidated') : 'pending',
                }} />
              ))}
              {(scorecard.predictions || []).map((p, i) => (
                <PredictionReceipt key={`p-${i}`} pred={p} />
              ))}
            </div>
          </>
        )}

        {/* ELO History */}
        {scorecard.elo_history?.length > 0 && (
          <>
            <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wider mb-3">
              ELO History
              <span className="ml-2 text-xs text-gray-500 font-normal normal-case">
                Conviction-weighted — contrarian correct calls earn more
              </span>
            </h3>
            <div className="space-y-1 mb-8">
              {[...scorecard.elo_history].reverse().map((h, i) => {
                const deltaColor = h.delta > 0 ? 'text-emerald-400' : h.delta < 0 ? 'text-red-400' : 'text-gray-500'
                const marketPct = Math.round((h.market_price_our_side || 0) * 100)
                const contrarian = marketPct < 40
                return (
                  <div key={i} className="flex items-center gap-3 text-xs border border-gray-800/50 rounded px-3 py-2">
                    <span className={`font-mono font-bold w-12 ${deltaColor}`}>
                      {h.delta > 0 ? '+' : ''}{h.delta?.toFixed(1)}
                    </span>
                    <span className="font-mono text-gray-400 w-16">
                      {h.old_rating?.toFixed(0)} → {h.new_rating?.toFixed(0)}
                    </span>
                    <span className={h.correct ? 'text-emerald-400' : 'text-red-400'}>
                      {h.correct ? '✓' : '✗'}
                    </span>
                    <span className="text-gray-300 flex-1 truncate">{h.prediction}</span>
                    <span className="text-gray-500">
                      {h.our_side?.toUpperCase()} @ {marketPct}%
                      {contrarian && <span className="ml-1 text-amber-400" title="Contrarian call">⚡</span>}
                    </span>
                    <span className="text-gray-600 uppercase text-[10px]">{h.platform}</span>
                  </div>
                )
              })}
            </div>
          </>
        )}

        {/* Best/worst frameworks */}
        {scorecard.best_frameworks?.length > 0 && (
          <>
            <h3 className="text-sm font-medium text-emerald-400 uppercase tracking-wider mb-3">Best Frameworks</h3>
            {scorecard.best_frameworks.map((fw, i) => (
              <div key={i} className="border border-gray-800 rounded-lg p-3 bg-gray-900/20 mb-2">
                <div className="flex justify-between mb-1">
                  <span className="text-sm text-white font-medium">{fw.name}</span>
                  <span className="text-xs text-emerald-400 font-mono">{fw.score != null ? (fw.score * 100).toFixed(0) + '%' : ''}</span>
                </div>
                <p className="text-xs text-gray-400">{fw.description}</p>
              </div>
            ))}
          </>
        )}
        {scorecard.weakest_frameworks?.length > 0 && (
          <>
            <h3 className="text-sm font-medium text-red-400 uppercase tracking-wider mb-3 mt-4">Weakest Frameworks</h3>
            {scorecard.weakest_frameworks.map((fw, i) => (
              <div key={i} className="border border-gray-800 rounded-lg p-3 bg-gray-900/20 mb-2">
                <div className="flex justify-between mb-1">
                  <span className="text-sm text-white font-medium">{fw.name}</span>
                  <span className="text-xs text-red-400 font-mono">{fw.score != null ? (fw.score * 100).toFixed(0) + '%' : ''}</span>
                </div>
                <p className="text-xs text-gray-400">{fw.description}</p>
              </div>
            ))}
          </>
        )}
      </div>
    )
  }

  if (selected && detailLoading) {
    return <div className="p-6 text-gray-400">Loading scorecard for {selected}...</div>
  }

  // ─── Guest leaderboard with search + sort ───
  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full">
      <div className="mb-6">
        <h2 className="text-lg font-medium text-white">Guest Scorecards</h2>
        <p className="text-sm text-gray-500">
          Every guest ranked by first-principles reasoning score. Click to verify.
        </p>
      </div>

      {/* Search + Sort controls */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search guests..."
          className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent"
        />
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
          className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-brand-accent"
        >
          {SORT_OPTIONS.map(opt => (
            <option key={opt.id} value={opt.id}>{opt.label}</option>
          ))}
        </select>
      </div>

      {/* Results count */}
      <p className="text-xs text-gray-600 mb-3">
        {filteredGuests.length} guest{filteredGuests.length !== 1 ? 's' : ''}
        {search && ` matching "${search}"`}
      </p>

      {filteredGuests.length === 0 ? (
        <div className="text-center py-12">
          <span className="text-3xl mb-3 block">📊</span>
          <p className="text-sm text-gray-400">
            {search ? `No guests matching "${search}"` : 'No guest data yet. Scorecards populate after content is analyzed.'}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredGuests.map((g, i) => (
            <button key={g.guest_name} onClick={() => loadScorecard(g.guest_name)}
              className="w-full text-left border border-gray-800 rounded-lg p-4 bg-gray-900/20 hover:bg-gray-900/50 hover:border-gray-700 transition-colors">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span className="text-gray-600 font-mono text-xs w-6">#{i + 1}</span>
                  <div>
                    <span className="text-white font-medium">{g.display_name || g.guest_name}</span>
                    {g.bio && <span className="text-xs text-gray-500 ml-2">{g.bio}</span>}
                  </div>
                  <SocialLinks x_handle={g.x_handle} linkedin_url={g.linkedin_url} website_url={g.website_url} />
                </div>
                <div className="flex items-center gap-3">
                  <GradeChip grade={g.reasoning_grade} />
                  <ELOBadge rating={g.elo_rating} count={g.elo_predictions_counted} />
                  <span className="text-xs text-gray-500">
                    {g.appearances} ep{g.appearances !== 1 ? 's' : ''}
                  </span>
                </div>
              </div>
              <ScoreBar score={g.avg_first_principles_score} />
              {g.consistency != null && (
                <div className="flex justify-between text-xs text-gray-600 mt-1">
                  <span>Range: {(g.worst_score * 100).toFixed(0)}% – {(g.best_score * 100).toFixed(0)}%</span>
                  <span>Consistency: {g.consistency < 0.15 ? 'High' : g.consistency < 0.3 ? 'Medium' : 'Low'}</span>
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
