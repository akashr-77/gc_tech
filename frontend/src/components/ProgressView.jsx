import { useState, useEffect, useRef } from 'react'
import ThinkingIndicator from './ThinkingIndicator'

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
    <div className="progress-view">
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
        <div className="card" style={{ padding: '2rem 1.5rem' }}>
          {/* Thinking Indicator replaces the old spinner + stage list */}
          <ThinkingIndicator
            stages={AGENT_STAGES}
            currentStageIndex={stageIdx}
            isActive={isRunning}
          />

          <p className="text-sm text-muted" style={{ textAlign: 'center', marginTop: '1.5rem' }}>
            ✨ The agent swarm is autonomously planning your event. This typically takes 3–8 minutes.
          </p>
        </div>
      )}
    </div>
  )
}
