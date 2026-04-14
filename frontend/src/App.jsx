import { useState, useRef } from 'react'
import PlanningForm from './components/PlanningForm'
import ProgressView from './components/ProgressView'
import ResultsDashboard from './components/ResultsDashboard'
import ChatSidebar from './components/ChatSidebar'

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
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [stoppedMsg, setStoppedMsg] = useState(null)
  const abortRef = useRef(null)
  const stopRequestedRef = useRef(false)

  // Called when the user submits the planning form
  const handlePlanSubmit = (id, input) => {
    stopRequestedRef.current = false
    setSessionId(id)
    setSessionData(null)
    setStoppedMsg(null)
    setView('progress')
    abortRef.current = new AbortController()
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
    if (stopRequestedRef.current) return
    setSessionData(data)
    setView('results')
    abortRef.current = null
    saveToHistory({ id: sessionId, status: data.status })
  }

  // Called when the user clicks a past session in the sidebar
  const handleViewSession = async (id) => {
    try {
      stopRequestedRef.current = false
      const res = await fetch(`/api/sessions/${id}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setSessionId(id)
      setSessionData(data)
      setStoppedMsg(null)
      if (data.status === 'working' || data.status === 'starting') {
        setView('progress')
      } else {
        setView('results')
      }
    } catch (e) {
      console.error('Failed to load session:', e)
    }
  }

  const handleNewChat = () => {
    stopRequestedRef.current = false
    setSessionId(null)
    setSessionData(null)
    setStoppedMsg(null)
    setView('home')
  }

  // END button handler — abort any in-flight work and return home
  const handleStop = () => {
    stopRequestedRef.current = true
    if (sessionId) {
      void fetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' })
        .catch((error) => console.error('Failed to cancel session:', error))
      saveToHistory({ id: sessionId, status: 'canceled' })
    }
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setStoppedMsg('Process stopped by user.')
    setView('home')
    setSessionData(null)
  }

  const toggleSidebar = () => setSidebarOpen((o) => !o)

  return (
    <div className="app">
      {/* Left sidebar */}
      <ChatSidebar
        isOpen={sidebarOpen}
        onToggle={toggleSidebar}
        onSelect={handleViewSession}
        onNewChat={handleNewChat}
        activeId={sessionId}
      />

      {/* Main area shifts when sidebar is open */}
      <div className={`app-main ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <header className="header">
          <div className="header-inner">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              {/* Sidebar toggle */}
              <button
                id="sidebar-toggle-btn"
                className="btn-ghost sidebar-toggle"
                onClick={toggleSidebar}
                title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M9 3v18" />
                </svg>
              </button>
              <div className="logo" onClick={handleNewChat}>
                <span className="logo-text">Intelligent Event Planner</span>
              </div>
            </div>
          </div>
        </header>

        <main className="main">
          {/* Stopped message banner */}
          {stoppedMsg && (
            <div className="stopped-banner">
              {stoppedMsg}
              <button className="btn-ghost" style={{ marginLeft: '1rem', fontSize: '.8rem' }} onClick={() => setStoppedMsg(null)}>Dismiss</button>
            </div>
          )}

          <div className="content-area">
            {view === 'home' && (
              <PlanningForm onSubmit={handlePlanSubmit} />
            )}
            {view === 'progress' && (
              <ProgressView
                sessionId={sessionId}
                onComplete={handlePlanComplete}
                onStop={handleStop}
                abortSignal={abortRef.current?.signal}
              />
            )}
            {view === 'results' && (
              <ResultsDashboard
                sessionId={sessionId}
                sessionData={sessionData}
                onBack={handleNewChat}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
