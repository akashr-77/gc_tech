import { useState, useEffect, useRef } from 'react'

const POLL_INTERVAL_MS = 3000

const STATUS_LABEL = {
  starting: 'Initialising…',
  working:  'Planning in progress…',
  completed:'Completed',
  failed:   'Failed',
}

const STATUS_ICON = {
  starting:  '🔄',
  working:   '🤖',
  completed: '✅',
  failed:    '❌',
}

const AGENT_STAGES = [
  { key: 'discover',   label: 'Discovering agents',       icon: '🔍' },
  { key: 'venue',      label: 'Sourcing venues',           icon: '🏛️' },
  { key: 'pricing',    label: 'Modelling ticket pricing',  icon: '💰' },
  { key: 'sponsor',    label: 'Identifying sponsors',      icon: '🤝' },
  { key: 'speaker',    label: 'Curating speakers',         icon: '🎤' },
  { key: 'exhibitor',  label: 'Planning exhibition floor', icon: '🗺️' },
  { key: 'community',  label: 'Building GTM strategy',     icon: '📣' },
  { key: 'compile',    label: 'Compiling final plan',      icon: '📋' },
]

export default function ProgressView({ sessionId, onComplete }) {
  const [status, setStatus] = useState('starting')
  const [error, setError]   = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [stageIdx, setStageIdx] = useState(0)
  const startRef = useRef(Date.now())
  const timerRef = useRef(null)
  const stageRef = useRef(null)

  // Elapsed time counter
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000))
    }, 1000)
    return () => clearInterval(timerRef.current)
  }, [])

  // Advance the visual stage every ~7 s while working
  useEffect(() => {
    if (status !== 'working' && status !== 'starting') return
    stageRef.current = setInterval(() => {
      setStageIdx((i) => Math.min(i + 1, AGENT_STAGES.length - 1))
    }, 7000)
    return () => clearInterval(stageRef.current)
  }, [status])

  // Poll the sessions endpoint
  useEffect(() => {
    if (!sessionId) return
    let cancelled = false

    const poll = async () => {
      try {
        const res = await fetch(`/api/sessions/${sessionId}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()

        if (cancelled) return
        setStatus(data.status)

        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(timerRef.current)
          clearInterval(stageRef.current)
          onComplete({ ...data, session_id: sessionId })
        }
      } catch (e) {
        if (!cancelled) setError(e.message)
      }
    }

    poll() // immediate first check
    const id = setInterval(poll, POLL_INTERVAL_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [sessionId, onComplete])

  const fmtElapsed = (s) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`
  }

  const isRunning = status === 'starting' || status === 'working'

  return (
    <div>
      <div className="flex-between mb-2">
        <div>
          <h2>{STATUS_ICON[status] || '⏳'} {STATUS_LABEL[status] || status}</h2>
          <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
            Session: <code style={{ fontSize: '.8rem', background: 'var(--bg)', padding: '.1rem .4rem', borderRadius: '4px' }}>{sessionId}</code>
          </p>
        </div>
        {isRunning && (
          <div style={{ textAlign: 'right' }}>
            <div className="text-sm text-muted">Elapsed</div>
            <div className="bold" style={{ fontSize: '1.2rem', fontVariantNumeric: 'tabular-nums' }}>{fmtElapsed(elapsed)}</div>
          </div>
        )}
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--error)', marginBottom: '1rem' }}>
          <p className="text-error">⚠️ {error}</p>
        </div>
      )}

      {isRunning && (
        <div className="card">
          {/* Spinner */}
          <div style={{ display: 'flex', justifyContent: 'center', padding: '1.5rem 0' }}>
            <div className="spinner" style={{ width: '56px', height: '56px' }} />
          </div>

          <p style={{ textAlign: 'center', marginBottom: '1.5rem', color: 'var(--text-muted)' }}>
            The agent swarm is autonomously planning your event. This typically takes 3–8 minutes.
          </p>

          {/* Stage tracker */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem' }}>
            {AGENT_STAGES.map((stage, idx) => {
              const done    = idx < stageIdx
              const current = idx === stageIdx
              const pending = idx > stageIdx
              return (
                <div key={stage.key} style={{
                  display: 'flex', alignItems: 'center', gap: '.75rem',
                  padding: '.55rem .85rem', borderRadius: 'var(--radius-sm)',
                  background: current ? 'rgba(59,130,246,.12)' : 'transparent',
                  border: current ? '1px solid rgba(59,130,246,.3)' : '1px solid transparent',
                  opacity: pending ? .4 : 1,
                  transition: 'all .3s ease',
                }}>
                  <span style={{ fontSize: '1.1rem', width: '24px', textAlign: 'center' }}>
                    {done ? '✅' : current ? stage.icon : '⭕'}
                  </span>
                  <span style={{
                    fontSize: '.9rem',
                    color: done ? 'var(--success)' : current ? 'var(--text)' : 'var(--text-muted)',
                    fontWeight: current ? 600 : 400,
                  }}>
                    {stage.label}
                  </span>
                  {current && (
                    <span style={{ marginLeft: 'auto', fontSize: '.75rem', color: 'var(--primary)' }}>
                      ● working
                    </span>
                  )}
                </div>
              )
            })}
          </div>

          <p className="text-sm text-muted mt-2" style={{ textAlign: 'center', marginTop: '1.25rem' }}>
            ✨ Tip: Agents run in parallel — results will appear once all specialists finish.
          </p>
        </div>
      )}
    </div>
  )
}
