import React, { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'

function CaptureBox({ onSave }) {
  const [body, setBody] = useState('')
  const [saving, setSaving] = useState(false)
  const [recording, setRecording] = useState(false)
  const [micSupported, setMicSupported] = useState(true)
  const [micError, setMicError] = useState(null)
  const textareaRef = useRef(null)
  const recognitionRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const silenceTimerRef = useRef(null)
  const audioChunksRef = useRef([])
  const recordingRef = useRef(false) // sync mirror of recording state for callbacks
  const bodyRef = useRef('') // sync mirror for callbacks that read current body

  // Feature detection on mount
  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    const hasMR = typeof window.MediaRecorder !== 'undefined' && navigator.mediaDevices?.getUserMedia
    if (!SR && !hasMR) setMicSupported(false)
  }, [])

  // Keep refs in sync
  useEffect(() => { bodyRef.current = body }, [body])
  useEffect(() => { recordingRef.current = recording }, [recording])

  // Shared save function — both typed and voice paths use this
  async function saveNote(text) {
    const trimmed = (text || '').trim()
    if (!trimmed || saving) return
    setSaving(true)
    try {
      const res = await fetch('/api/notes/quick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: trimmed }),
      })
      if (!res.ok) throw new Error('Save failed')
      const note = await res.json()
      setBody('')
      onSave(note)
    } catch (e) {
      console.error('Quick save failed:', e)
    } finally {
      setSaving(false)
    }
  }

  function handleKeyDown(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      saveNote(body)
    }
  }

  // ─── Voice recording ───

  function clearSilenceTimer() {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
  }

  function resetSilenceTimer(onSilence) {
    clearSilenceTimer()
    silenceTimerRef.current = setTimeout(onSilence, 1500)
  }

  function startRecording() {
    setMicError(null)
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (SR) {
      startBrowserSR(SR)
    } else {
      startWhisperFallback()
    }
  }

  function cancelRecording() {
    clearSilenceTimer()
    setRecording(false)
    // Stop browser SR if active
    if (recognitionRef.current) {
      try { recognitionRef.current.abort() } catch (_) {}
      recognitionRef.current = null
    }
    // Stop MediaRecorder if active
    if (mediaRecorderRef.current) {
      try { mediaRecorderRef.current.stop() } catch (_) {}
      mediaRecorderRef.current = null
      audioChunksRef.current = []
    }
    // Leave textarea content for manual editing
  }

  // ─── Browser SpeechRecognition path ───

  function startBrowserSR(SR) {
    const recognition = new SR()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'
    recognitionRef.current = recognition

    let finalTranscript = ''
    let cancelled = false

    recognition.onstart = () => {
      setRecording(true)
    }

    recognition.onresult = (event) => {
      let interim = ''
      finalTranscript = ''
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          finalTranscript += result[0].transcript
        } else {
          interim += result[0].transcript
        }
      }
      setBody(finalTranscript + interim)
      resetSilenceTimer(() => {
        if (recordingRef.current) {
          try { recognition.stop() } catch (_) {}
        }
      })
    }

    recognition.onerror = (event) => {
      clearSilenceTimer()
      if (event.error === 'network' || event.error === 'service-not-allowed') {
        // Fall through to Whisper
        recognitionRef.current = null
        setRecording(false)
        startWhisperFallback()
        return
      }
      if (event.error === 'not-allowed') {
        setMicError('Microphone access denied \u2014 enable in browser settings')
      }
      cancelled = true
      setRecording(false)
      recognitionRef.current = null
    }

    recognition.onend = () => {
      clearSilenceTimer()
      recognitionRef.current = null
      if (!cancelled && recordingRef.current) {
        // Ended via silence — save
        setRecording(false)
        saveNote(bodyRef.current)
      }
    }

    try {
      recognition.start()
    } catch (e) {
      console.error('SR start failed:', e)
      setMicError('Could not start voice recognition')
    }
  }

  // ─── Whisper fallback path ───

  async function startWhisperFallback() {
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (e) {
      setMicError('Microphone access denied \u2014 enable in browser settings')
      return
    }

    setRecording(true)
    audioChunksRef.current = []

    // Pick supported MIME type
    const mimeTypes = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
    let mimeType = ''
    for (const mt of mimeTypes) {
      if (MediaRecorder.isTypeSupported(mt)) { mimeType = mt; break }
    }

    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {})
    mediaRecorderRef.current = recorder

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data)
    }

    recorder.onstop = async () => {
      // Stop all tracks
      stream.getTracks().forEach(t => t.stop())

      if (audioChunksRef.current.length === 0) {
        setRecording(false)
        mediaRecorderRef.current = null
        return
      }

      const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' })
      audioChunksRef.current = []
      mediaRecorderRef.current = null

      // Send to Whisper backend
      setBody('Transcribing\u2026')
      try {
        const form = new FormData()
        form.append('audio', blob, 'recording.' + (recorder.mimeType?.includes('mp4') ? 'mp4' : 'webm'))
        const res = await fetch('/api/notes/transcribe', { method: 'POST', body: form })
        if (!res.ok) throw new Error(`Transcribe failed: ${res.status}`)
        const { transcript } = await res.json()
        if (transcript?.trim()) {
          setBody(transcript)
          setRecording(false)
          saveNote(transcript)
        } else {
          setBody('')
          setRecording(false)
        }
      } catch (e) {
        console.error('Whisper transcription failed:', e)
        setBody('')
        setRecording(false)
        setMicError('Transcription failed \u2014 check Whisper server config')
      }
    }

    recorder.start(250) // collect data every 250ms

    // Escape hatch: 30-second hard max recording length.
    // RMS-based silence detection deferred as follow-up.
    silenceTimerRef.current = setTimeout(() => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop()
      }
    }, 30000)
  }

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.max(72, el.scrollHeight) + 'px'
    }
  }, [body])

  return (
    <div className="border border-border rounded-lg bg-surface p-4">
      <textarea
        ref={textareaRef}
        value={body}
        onChange={e => setBody(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="What are you thinking?"
        rows={3}
        className="w-full bg-transparent text-text-primary placeholder-text-secondary text-sm leading-relaxed resize-none focus:outline-none"
      />
      <div className="flex items-center justify-between mt-2">
        <span className="text-xs text-text-secondary">
          {micError ? (
            <span className="text-red-400" title={micError}>🎤✕ {micError}</span>
          ) : (
            body.length > 200 ? `${body.length} chars` : ''
          )}
        </span>
        <div className="flex items-center gap-3">
          {micSupported && (
            <button
              type="button"
              onClick={() => recording ? cancelRecording() : startRecording()}
              className={`text-sm px-3 py-1.5 rounded transition-colors ${
                recording
                  ? 'bg-brand-accent text-white animate-pulse'
                  : 'bg-brand-accent text-white hover:bg-red-500'
              }`}
              aria-label={recording ? 'Stop recording' : 'Start voice dictation'}
            >
              {recording ? '● Listening' : '🎤'}
            </button>
          )}
          <span className="text-xs text-text-secondary">⌘ Enter</span>
          <button
            onClick={() => saveNote(body)}
            disabled={!body.trim() || saving}
            className="text-sm px-4 py-1.5 rounded bg-brand-accent text-white hover:bg-red-500 disabled:bg-gray-700 disabled:text-gray-500 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

function EchoCard({ note, echo, collapsed, onCollapse }) {
  if (collapsed) {
    return (
      <div 
        onClick={() => onCollapse(false)}
        className="border border-border rounded-lg bg-surface px-4 py-2 cursor-pointer hover:bg-gray-800 transition-colors"
      >
        <p className="text-xs text-text-secondary truncate">
          {note.body.slice(0, 80)}{note.body.length > 80 ? '…' : ''}
          {echo && echo.matching_notes.length > 0 && (
            <span className="text-purple-400 ml-2">
              {echo.matching_notes.length} note{echo.matching_notes.length !== 1 ? 's' : ''} echoed
            </span>
          )}
        </p>
      </div>
    )
  }

  return (
    <div className="border border-border rounded-lg bg-surface overflow-hidden">
      {/* Saved note header */}
      <div className="px-4 py-3 border-b border-border flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-text-primary leading-relaxed">{note.body}</p>
          <p className="text-xs text-text-secondary mt-1 font-mono">
            Saved {new Date(note.created_at).toLocaleTimeString()}
          </p>
        </div>
        <button
          onClick={() => onCollapse(true)}
          className="text-xs text-text-secondary hover:text-text-primary ml-2"
        >
          ▲
        </button>
      </div>

      {/* Echo results */}
      {!echo ? (
        <div className="px-4 py-3">
          <p className="text-xs text-text-secondary animate-pulse">Looking for connections…</p>
        </div>
      ) : (
        <div className="px-4 py-3 space-y-3">
          {echo.matching_notes.length === 0 && echo.matching_content.length === 0 ? (
            <p className="text-xs text-text-secondary">No echoes in the archive. New territory.</p>
          ) : (
            <>
              {/* Matching notes */}
              {echo.matching_notes.map(match => (
                <a 
                  key={match.note_id} 
                  href={`/notes/${match.note_id}`}
                  className="block border border-border rounded p-2 hover:bg-gray-800 transition-colors"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs bg-purple-900/40 text-purple-300 border border-purple-800 px-1.5 py-0.5 rounded">
                      note
                    </span>
                    {match.conviction_tier && (
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${
                        match.conviction_tier === 'axiom' ? 'bg-red-900/40 text-red-300 border-red-800' :
                        match.conviction_tier === 'thesis' ? 'bg-amber-900/40 text-amber-300 border-amber-800' :
                        'bg-gray-700 text-gray-300 border-gray-600'
                      }`}>
                        {match.conviction_tier}
                      </span>
                    )}
                    <span className="text-xs font-mono text-text-secondary ml-auto">
                      {Math.round(match.similarity * 100)}%
                    </span>
                  </div>
                  <p className="text-xs text-text-primary">
                    {match.title || match.body_preview}
                  </p>
                </a>
              ))}

              {/* Matching content — speaker attribution first */}
              {echo.matching_content.map(match => (
                <div 
                  key={match.item_id}
                  className="border border-border rounded p-2"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs bg-cyan-900/40 text-cyan-300 border border-cyan-800 px-1.5 py-0.5 rounded">
                      source
                    </span>
                    {match.authors && match.authors.length > 0 && (
                      <span className="text-xs font-medium text-text-primary">
                        {match.authors.join(', ')}
                      </span>
                    )}
                    <span className="text-xs font-mono text-text-secondary ml-auto">
                      {Math.round(match.similarity * 100)}%
                    </span>
                  </div>
                  <p className="text-xs text-text-secondary mb-1">{match.item_title}</p>
                  {match.feed_name && (
                    <p className="text-xs text-text-secondary italic">{match.feed_name}</p>
                  )}
                  <p className="text-xs text-text-primary mt-1">{match.chunk_preview}</p>
                </div>
              ))}
            </>
          )}

          {echo.resurfacing_count > 0 && (
            <p className="text-xs text-purple-400">
              {echo.resurfacing_count} note{echo.resurfacing_count !== 1 ? 's' : ''} resurfaced by this thought
            </p>
          )}
        </div>
      )}
    </div>
  )
}

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
  const [resurfacingCount, setResurfacingCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [echoCards, setEchoCards] = useState([])

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
      // Load resurfacing count
      loadResurfacingCount()
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  async function loadResurfacingCount() {
    try {
      const res = await fetch('/api/resurfacing/count')
      if (res.ok) {
        const data = await res.json()
        setResurfacingCount(data.count)
      }
    } catch (e) {}
  }

  async function handleCapture(savedNote) {
    // Add card with no echo yet
    const cardId = savedNote.note_id
    setEchoCards(prev => [{ id: cardId, note: savedNote, echo: null, collapsed: false }, ...prev])

    // Collapse previous cards
    setEchoCards(prev => prev.map((card, i) =>
      i === 0 ? card : { ...card, collapsed: true }
    ))

    // Fetch echo
    try {
      const res = await fetch(`/api/notes/${savedNote.note_id}/echo`)
      if (res.ok) {
        const echoData = await res.json()
        setEchoCards(prev => prev.map(card =>
          card.id === cardId ? { ...card, echo: echoData } : card
        ))
      }
    } catch (e) {
      console.error('Echo fetch failed:', e)
      setEchoCards(prev => prev.map(card =>
        card.id === cardId ? { ...card, echo: { matching_notes: [], matching_content: [], resurfacing_count: 0 } } : card
      ))
    }

    // Auto-collapse after 60 seconds
    setTimeout(() => {
      setEchoCards(prev => prev.map(card =>
        card.id === cardId ? { ...card, collapsed: true } : card
      ))
    }, 60000)

    // Refresh the resurfacing count in review queue
    loadResurfacingCount()
  }

  return (
    <div className="p-6 max-w-4xl mx-auto overflow-y-auto h-full space-y-8">
      {/* Capture box — FIRST THING */}
      <CaptureBox onSave={handleCapture} />

      {/* Echo cards */}
      {echoCards.length > 0 && (
        <div className="space-y-2">
          {echoCards.map(card => (
            <EchoCard
              key={card.id}
              note={card.note}
              echo={card.echo}
              collapsed={card.collapsed}
              onCollapse={(val) => setEchoCards(prev =>
                prev.map(c => c.id === card.id ? { ...c, collapsed: val } : c)
              )}
            />
          ))}
        </div>
      )}

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
            count={resurfacingCount}
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