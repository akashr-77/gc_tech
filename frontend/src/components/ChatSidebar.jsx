import { useState, useEffect, useRef } from 'react'

const HISTORY_KEY = 'mp_sessions'

function getHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]') }
  catch { return [] }
}

function clearHistory() {
  localStorage.removeItem(HISTORY_KEY)
}

const DOMAIN_ICON = {
  conference:     '🏛️',
  music_festival: '🎵',
  sporting_event: '🏆',
}

function StatusDot({ status }) {
  const color = {
    completed: 'var(--success)',
    working:   'var(--warn)',
    starting:  'var(--primary)',
    failed:    'var(--error)',
  }[status] || 'var(--text-muted)'

  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: color, flexShrink: 0,
    }} />
  )
}

function timeAgo(isoString) {
  if (!isoString) return ''
  const diff = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(isoString).toLocaleDateString()
}

export default function ChatSidebar({ isOpen, onToggle, onSelect, onNewChat, activeId }) {
  const [history, setHistory] = useState([])
  const sidebarRef = useRef(null)

  useEffect(() => {
    setHistory(getHistory())
    const id = setInterval(() => setHistory(getHistory()), 5000)
    return () => clearInterval(id)
  }, [])

  // Close sidebar on outside click (mobile)
  useEffect(() => {
    const handleClick = (e) => {
      if (isOpen && sidebarRef.current && !sidebarRef.current.contains(e.target)) {
        const toggle = document.getElementById('sidebar-toggle-btn')
        if (toggle && toggle.contains(e.target)) return
        if (window.innerWidth < 768) {
          onToggle()
        }
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [isOpen, onToggle])

  const handleClear = () => {
    clearHistory()
    setHistory([])
  }

  return (
    <>
      {/* Mobile backdrop overlay */}
      <div className={`sidebar-backdrop ${isOpen ? 'visible' : ''}`} onClick={onToggle} />

      <div ref={sidebarRef} className={`chat-sidebar ${isOpen ? 'open' : ''}`}>
        {/* New Chat button */}
        <div className="sidebar-top">
          <button className="sidebar-new-chat" onClick={onNewChat} id="new-chat-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New Chat
          </button>
          <button className="sidebar-close-btn" onClick={onToggle} title="Close sidebar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M9 3v18" />
            </svg>
          </button>
        </div>

        {/* Session list */}
        <div className="sidebar-sessions">
          {history.length === 0 ? (
            <p className="sidebar-empty">
              No conversations yet.<br />Start a new plan to begin!
            </p>
          ) : (
            <>
              <div className="sidebar-section-label">Recent</div>
              {history.map((session) => (
                <button
                  key={session.id}
                  className={`sidebar-session-item ${activeId === session.id ? 'active' : ''}`}
                  onClick={() => onSelect(session.id)}
                >
                  <div className="sidebar-session-row">
                    <span className="sidebar-session-icon">
                      {DOMAIN_ICON[session.domain] || '📋'}
                    </span>
                    <span className="sidebar-session-title">
                      {session.topic || 'Untitled Plan'}
                    </span>
                    <StatusDot status={session.status} />
                  </div>
                  <div className="sidebar-session-meta">
                    {session.city && <span>{session.city}</span>}
                    {session.startedAt && <span>{timeAgo(session.startedAt)}</span>}
                  </div>
                </button>
              ))}
            </>
          )}
        </div>

        {/* Bottom actions */}
        {history.length > 0 && (
          <div className="sidebar-bottom">
            <button className="sidebar-clear-btn" onClick={handleClear}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
              Clear all
            </button>
          </div>
        )}
      </div>
    </>
  )
}
