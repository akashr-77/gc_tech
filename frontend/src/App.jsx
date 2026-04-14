import { useState } from 'react'
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

  const handleNewChat = () => {
    setSessionId(null)
    setSessionData(null)
    setView('home')
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
                <span className="logo-icon">⚡</span>
                <span className="logo-text">Manhattan Project</span>
              </div>
            </div>
            <nav style={{ display: 'flex', gap: '0.5rem' }}>
              {view !== 'home' && (
                <button className="btn-ghost" onClick={handleNewChat}>
                  ← New Plan
                </button>
              )}
            </nav>
          </div>
        </header>

        <main className="main">
          <div className="content-area">
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
                onBack={handleNewChat}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
