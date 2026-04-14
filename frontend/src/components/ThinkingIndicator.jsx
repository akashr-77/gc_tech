import { useState, useEffect } from 'react'

const THINKING_MESSAGES = [
  'Searching data…',
  'Analyzing inputs…',
  'Formulating venue options…',
  'Evaluating alternatives…',
  'Generating final response…',
]

export default function ThinkingIndicator({ stages, currentStageIndex, isActive }) {
  const [msgIdx, setMsgIdx] = useState(0)
  const [detailsOpen, setDetailsOpen] = useState(false)

  // Cycle through thinking messages
  useEffect(() => {
    if (!isActive) return
    const interval = setInterval(() => {
      setMsgIdx((i) => (i + 1) % THINKING_MESSAGES.length)
    }, 3200)
    return () => clearInterval(interval)
  }, [isActive])

  if (!isActive) return null

  const currentStage = stages[currentStageIndex] || stages[0]

  return (
    <div className="thinking-indicator">
      {/* Main thinking bubble */}
      <div className="thinking-bubble">
        <div className="thinking-header">
          <button
            className="thinking-toggle"
            onClick={() => setDetailsOpen(!detailsOpen)}
          >
            <span className="thinking-label">{currentStage.label}</span>
            <span className="thinking-toggle-text">{detailsOpen ? 'Hide details' : 'Details'}</span>
          </button>
        </div>

        {/* Shimmer effect */}
        <div className="shimmer-container">
          <div className="shimmer-bar shimmer-bar-wide" />
          <div className="shimmer-bar shimmer-bar-medium" />
          <div className="shimmer-bar shimmer-bar-narrow" />
        </div>

        {/* Dynamic status message with typing dots */}
        <div className="thinking-status">
          <span className="thinking-status-text" key={msgIdx}>
            {THINKING_MESSAGES[msgIdx]}
          </span>
          <span className="typing-dots">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </span>
        </div>
      </div>

      {/* Expandable stage details */}
      <div className={`thinking-details ${detailsOpen ? 'open' : ''}`}>
        <div className="thinking-details-inner">
          {stages.map((stage, idx) => {
            const done = idx < currentStageIndex
            const current = idx === currentStageIndex
            const pending = idx > currentStageIndex
            return (
              <div
                key={stage.key}
                className={`thinking-stage ${done ? 'done' : ''} ${current ? 'current' : ''} ${pending ? 'pending' : ''}`}
              >
                <span className="thinking-stage-icon">
                  {done ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" fill="var(--success)" opacity="0.15" />
                      <path d="M8 12l3 3 5-5" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : current ? (
                    <div className="stage-pulse-dot" />
                  ) : (
                    <div className="stage-pending-dot" />
                  )}
                </span>
                <span className="thinking-stage-label">{stage.label}</span>
                {current && <span className="thinking-stage-active">working</span>}
                {done && <span className="thinking-stage-done">done</span>}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
