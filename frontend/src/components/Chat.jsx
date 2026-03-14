import React, { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

const EXAMPLE_QUERIES = [
  "Show me the top 5 frameworks",
  "What am I not talking about?",
  "How has my view on the Fed evolved?",
  "Who has the best prediction track record?",
]

function SourceBadge({ source }) {
  const colors = {
    content: 'bg-blue-900/40 text-blue-300 border-blue-800',
    thesis_element: 'bg-amber-900/40 text-amber-300 border-amber-800',
    framework: 'bg-purple-900/40 text-purple-300 border-purple-800',
    blind_spot: 'bg-red-900/40 text-red-300 border-red-800',
  }
  const cls = colors[source.type] || 'bg-gray-800 text-gray-300 border-gray-700'
  const label = source.title || source.guest_name || source.topic || source.type

  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded border ${cls}`}>
      {label}
    </span>
  )
}

function Message({ msg }) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-2xl bg-gray-800 rounded-2xl rounded-tr-md px-4 py-3 text-sm text-gray-100">
          {msg.content}
        </div>
      </div>
    )
  }

  return (
    <div className="mb-6">
      <div className="max-w-3xl">
        <div className="prose prose-invert prose-sm max-w-none text-gray-200 leading-relaxed">
          <ReactMarkdown>{msg.content}</ReactMarkdown>
        </div>
        {msg.sources && msg.sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            <span className="text-xs text-gray-500 mr-1 self-center">Sources:</span>
            {msg.sources.map((s, i) => <SourceBadge key={i} source={s} />)}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage(text) {
    if (!text.trim()) return
    const userMsg = { role: 'user', content: text.trim() }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('/api/chat/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text.trim() }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response || data.detail || 'No response received.',
        sources: data.sources || [],
      }])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.message}. Make sure the service is running and an LLM API key is configured.`,
        sources: [],
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    sendMessage(input)
  }

  const isEmpty = messages.length === 0

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-xl bg-brand-accent/20 flex items-center justify-center mb-6">
              <span className="text-3xl">🧠</span>
            </div>
            <h2 className="text-xl font-medium text-white mb-2">Ten31 Thoughts</h2>
            <p className="text-gray-400 text-sm max-w-md mb-8">
              Your macro intelligence layer. Ask about frameworks, predictions,
              blind spots, or how your thesis compares to external voices.
            </p>
            <div className="grid grid-cols-2 gap-2 max-w-lg w-full">
              {EXAMPLE_QUERIES.map(q => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="text-left text-sm px-4 py-3 rounded-lg border border-gray-800 text-gray-300 hover:border-gray-600 hover:text-white transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => <Message key={i} msg={msg} />)}
            {loading && (
              <div className="mb-4">
                <div className="flex gap-1.5 px-1">
                  <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-gray-800 px-6 py-4 shrink-0">
        <form onSubmit={handleSubmit} className="flex gap-3 max-w-3xl mx-auto">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask about frameworks, predictions, blind spots..."
            disabled={loading}
            className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-accent transition-colors disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-brand-accent hover:bg-brand-accent/80 disabled:bg-gray-700 disabled:text-gray-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  )
}
