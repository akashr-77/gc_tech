import { useState } from 'react'
import PlanningForm from './components/PlanningForm'
import ProgressView from './components/ProgressView'
import ResultsDashboard from './components/ResultsDashboard'
import SessionHistory from './components/SessionHistory'

// Simple session history stored in localStorage
const HISTORY_KEY = 'mp_sessions'

function getHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]') }
  catch { return [] }
}

function saveToHistory(entry) {
  const history = getHistory()
  const existing = history.findIndex(h => h.id === entry.id)
  if (existing >= 0) history[existing] = { ...history[existing], ...entry }
  else history.unshift(entry)
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 30)))
}

export default function App() {
  const [view, setView] = useState('home')   // 'home' | 'progress' | 'results'
  const [sessionId, setSessionId] = useState(null)
  const [sessionData, setSessionData] = useState(null)

  // Called when the user submits the planning form
  const handlePlanSubmit = (id, input) => {
    setSessionId(id)
    setSessionData(null)
    setView('progress')
    saveToHistory({
      id,
      topic: input.topic,
      city: input.city,
      domain: input.domain,
      status: 'working',
      startedAt: new Date().toISOString(),
    })
  }

  // Called when the ProgressView detects a terminal state
  const handlePlanComplete = (data) => {
    setSessionData(data)
    setView('results')
    saveToHistory({ id: sessionId, status: data.status })
  }

  // Called when the user clicks a past session in the sidebar
  const handleViewSession = async (id) => {
    try {
      const res = await fetch(`/api/sessions/${id}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setSessionId(id)
      setSessionData(data)
      if (data.status === 'working' || data.status === 'starting') {
        setView('progress')
      } else {
        setView('results')
      }
    } catch (e) {
      console.error('Failed to load session:', e)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="logo" onClick={() => setView('home')}>
            <span className="logo-icon">⚡</span>
            <span className="logo-text">Manhattan Project</span>
          </div>
          <nav style={{ display: 'flex', gap: '0.5rem' }}>
            {view !== 'home' && (
              <button className="btn-ghost" onClick={() => setView('home')}>
                ← New Plan
              </button>
            )}
          </nav>
        </div>
      </header>

      <main className="main">
        <div className="layout">
          <div className="content">
            {view === 'home' && (
              <PlanningForm onSubmit={handlePlanSubmit} />
            )}
            {view === 'progress' && (
              <ProgressView
                sessionId={sessionId}
                onComplete={handlePlanComplete}
              />
            )}
            {view === 'results' && (
              <ResultsDashboard
                sessionId={sessionId}
                sessionData={sessionData}
                onBack={() => setView('home')}
              />
            )}
          </div>

          <aside className="sidebar">
            <SessionHistory
              onSelect={handleViewSession}
              activeId={sessionId}
            />
          </aside>
        </div>
      </main>
    </div>
  )
}
