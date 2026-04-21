import React, { useState, useEffect } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import Login from './components/Login'
import ThisWeek from './components/ThisWeek'
import Notes from './components/Notes'
import NoteDetail from './components/NoteDetail'
import Connections from './components/Connections'
import Signals from './components/Signals'
import Sources from './components/Sources'
import Ask from './components/Ask'
import System from './components/System'

function Header() {
  const location = useLocation()
  
  const navItems = [
    { path: '/', label: 'This Week' },
    { path: '/notes', label: 'Notes' },
    { path: '/connections', label: 'Connections' },
    { path: '/sources', label: 'Sources' },
    { path: '/ask', label: 'Ask' },
  ]

  function isActive(path) {
    if (path === '/') {
      return location.pathname === '/'
    }
    return location.pathname.startsWith(path)
  }

  return (
    <header className="h-12 border-b border-border bg-surface flex items-center justify-between px-6">
      <Link to="/" className="font-mono text-sm tracking-wider text-text-primary">
        TEN31
      </Link>
      
      <nav className="flex items-center gap-8">
        {navItems.map(({ path, label }) => (
          <Link
            key={path}
            to={path}
            className={`text-sm transition-colors relative ${
              isActive(path)
                ? 'text-text-primary border-b-2 border-brand-accent'
                : 'text-text-secondary hover:text-text-primary'
            }`}
          >
            {label}
          </Link>
        ))}
      </nav>

      <Link 
        to="/system" 
        className="text-xs text-text-secondary hover:text-text-primary transition-colors"
      >
        system
      </Link>
    </header>
  )
}

export default function App() {
  const [authChecked, setAuthChecked] = useState(false)
  const [needsLogin, setNeedsLogin] = useState(false)

  useEffect(() => {
    fetch('/api/auth/status', { credentials: 'include' })
      .then((res) => res.json())
      .then((data) => {
        if (data.authEnabled && !data.authenticated) {
          setNeedsLogin(true)
        }
        setAuthChecked(true)
      })
      .catch(() => setAuthChecked(true))
  }, [])

  if (!authChecked) {
    return <div className="min-h-screen" style={{ background: '#0a0a0c' }} />
  }

  if (needsLogin) {
    return <Login onLogin={() => setNeedsLogin(false)} />
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<ThisWeek />} />
          <Route path="/notes" element={<Notes />} />
          <Route path="/notes/:noteId" element={<NoteDetail />} />
          <Route path="/connections" element={<Connections />} />
          <Route path="/connections/signals" element={<Signals />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="/ask" element={<Ask />} />
          <Route path="/system" element={<System />} />
        </Routes>
      </main>
    </div>
  )
}