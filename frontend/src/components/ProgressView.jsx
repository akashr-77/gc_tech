import { useState, useEffect, useRef } from 'react'
import ThinkingIndicator from './ThinkingIndicator'

const POLL_INTERVAL_MS = 3000

const STATUS_LABEL = {
  starting: 'Initialising…',
  working:  'Planning in progress…',
  completed:'Completed',
  failed:   'Failed',
  canceled: 'Stopped',
}



const AGENT_STAGES = [
  { key: 'discover',   label: 'Discovering agents' },
  { key: 'venue',      label: 'Sourcing venues' },
  { key: 'pricing',    label: 'Modelling ticket pricing' },
  { key: 'sponsor',    label: 'Identifying sponsors' },
  { key: 'speaker',    label: 'Curating speakers' },
  { key: 'exhibitor',  label: 'Planning exhibition floor' },
  { key: 'community',  label: 'Building GTM strategy' },
  { key: 'compile',    label: 'Compiling final plan' },
]

export default function ProgressView({ sessionId, onComplete, onStop, abortSignal }) {
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
    let intervalId = null

    const clearWork = () => {
      clearInterval(timerRef.current)
      clearInterval(stageRef.current)
      if (intervalId) clearInterval(intervalId)
    }

    const handleAbort = () => {
      cancelled = true
      clearWork()
      setStatus('canceled')
    }

    if (abortSignal?.aborted) {
      handleAbort()
      return undefined
    }

    abortSignal?.addEventListener('abort', handleAbort)

    const poll = async () => {
      try {
        const res = await fetch(`/api/sessions/${sessionId}`, { signal: abortSignal })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()

        if (cancelled || abortSignal?.aborted) return
        setStatus(data.status)

        if (data.status === 'completed' || data.status === 'failed' || data.status === 'canceled') {
          clearWork()
          onComplete({ ...data, session_id: sessionId })
        }
      } catch (e) {
        if (abortSignal?.aborted || e?.name === 'AbortError') {
          handleAbort()
          return
        }
        if (!cancelled) setError(e.message)
      }
    }

    poll() // immediate first check
    intervalId = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearWork()
      abortSignal?.removeEventListener('abort', handleAbort)
    }
  }, [sessionId, onComplete, abortSignal])

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
          <h2>{STATUS_LABEL[status] || status}</h2>
          <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
            Session: <code style={{ fontSize: '.8rem', background: 'var(--bg)', padding: '.1rem .4rem', borderRadius: '4px' }}>{sessionId}</code>
          </p>
        </div>
        {isRunning && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ textAlign: 'right' }}>
              <div className="text-sm text-muted">Elapsed</div>
              <div className="bold" style={{ fontSize: '1.2rem', fontVariantNumeric: 'tabular-nums' }}>{fmtElapsed(elapsed)}</div>
            </div>
            <button className="btn btn-end" onClick={onStop} title="Stop processing">
              END
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--error)', marginBottom: '1rem' }}>
          <p className="text-error">{error}</p>
        </div>
      )}

      {isRunning && (
        <div className="card" style={{ padding: '2rem 1.5rem' }}>
          <ThinkingIndicator
            stages={AGENT_STAGES}
            currentStageIndex={stageIdx}
            isActive={isRunning}
          />

          <p className="text-sm text-muted" style={{ textAlign: 'center', marginTop: '1.5rem' }}>
            The agent swarm is autonomously planning your event. This typically takes 3-8 minutes.
          </p>
        </div>
      )}
    </div>
  )
}
