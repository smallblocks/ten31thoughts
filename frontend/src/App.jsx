import React, { useState } from 'react'
import Chat from './components/Chat'
import Feeds from './components/Feeds'
import Briefings from './components/Briefings'
import Status from './components/Status'

const TABS = [
  { id: 'chat', label: 'Chat', icon: '💬' },
  { id: 'briefings', label: 'Briefings', icon: '📋' },
  { id: 'feeds', label: 'Feeds', icon: '📡' },
  { id: 'status', label: 'Status', icon: '⚙️' },
]

export default function App() {
  const [tab, setTab] = useState('chat')

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-brand-accent flex items-center justify-center text-sm font-semibold text-white">T</div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-white">Ten31 Thoughts</h1>
            <p className="text-xs text-gray-500">Macro Intelligence Service</p>
          </div>
        </div>
        <nav className="flex gap-1">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded text-sm transition-colors ${
                tab === t.id
                  ? 'bg-gray-800 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`}
            >
              <span className="mr-1.5">{t.icon}</span>{t.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-hidden">
        {tab === 'chat' && <Chat />}
        {tab === 'briefings' && <Briefings />}
        {tab === 'feeds' && <Feeds />}
        {tab === 'status' && <Status />}
      </main>
    </div>
  )
}
