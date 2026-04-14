import { useState, useEffect } from 'react'

const HISTORY_KEY = 'mp_sessions'

function getHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]') }
  catch { return [] }
}

function clearHistory() {
  localStorage.removeItem(HISTORY_KEY)
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

export default function SessionHistory({ onSelect, activeId }) {
  const [history, setHistory] = useState([])
  const [, forceUpdate] = useState(0)

  useEffect(() => {
    setHistory(getHistory())
    // Refresh every 5 s in case another tab updates localStorage
    const id = setInterval(() => setHistory(getHistory()), 5000)
    return () => clearInterval(id)
  }, [forceUpdate])

  const handleClear = () => {
    clearHistory()
    setHistory([])
  }

  return (
    <div className="card" style={{ padding: '1.25rem' }}>
      <div className="flex-between mb-2" style={{ marginBottom: '1rem' }}>
        <h3 style={{ margin: 0 }}>Past Sessions</h3>
        {history.length > 0 && (
          <button
            className="btn-ghost"
            style={{ fontSize: '.75rem', padding: '.25rem .6rem', color: 'var(--error)' }}
            onClick={handleClear}
            title="Clear history"
          >
            Clear
          </button>
        )}
      </div>

      {history.length === 0 ? (
        <p className="text-sm text-muted">
          No past sessions yet. Submit the form to start planning!
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem' }}>
          {history.map((session) => (
            <button
              key={session.id}
              onClick={() => onSelect(session.id)}
              style={{
                background: activeId === session.id ? 'rgba(59,130,246,.12)' : 'var(--bg)',
                border: `1px solid ${activeId === session.id ? 'rgba(59,130,246,.4)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-sm)',
                padding: '.65rem .85rem',
                textAlign: 'left',
                width: '100%',
                cursor: 'pointer',
                transition: 'all .15s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.2rem' }}>
                <span style={{
                  fontSize: '.88rem', fontWeight: 600, color: 'var(--text)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
                }}>
                  {session.topic || session.id}
                </span>
                <StatusDot status={session.status} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', fontSize: '.75rem', color: 'var(--text-muted)' }}>
                {session.city && <span>{session.city}</span>}
                {session.startedAt && (
                  <span>· {new Date(session.startedAt).toLocaleDateString()}</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
