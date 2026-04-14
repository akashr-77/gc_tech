import { useState } from 'react'

const DOMAINS = [
  { value: 'conference',      label: 'Conference' },
  { value: 'music_festival',  label: 'Music Festival' },
  { value: 'sporting_event',  label: 'Sporting Event' },
]

const DEFAULTS = {
  topic: '',
  domain: 'conference',
  city: '',
  country: '',
  budget_usd: '',
  target_audience: '',
  dates: '',
}

export default function PlanningForm({ onSubmit }) {
  const [form, setForm] = useState(DEFAULTS)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const update = (field) => (e) =>
    setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)

    const payload = {
      ...form,
      budget_usd:      parseInt(form.budget_usd, 10),
      target_audience: parseInt(form.target_audience, 10),
    }

    if (!payload.topic || !payload.city || !payload.country || !payload.dates) {
      setError('Please fill in all required fields.')
      return
    }

    setLoading(true)
    try {
      const res = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const msg = await res.text()
        throw new Error(msg || `HTTP ${res.status}`)
      }
      const data = await res.json()
      onSubmit(data.session_id, form)
    } catch (err) {
      setError(err.message || 'Failed to start planning session.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      {/* Hero */}
      <div className="mb-2" style={{ marginBottom: '2rem' }}>
        <h1 style={{ marginBottom: '.5rem' }}>
          AI-Powered Event Planner
        </h1>
        <p style={{ fontSize: '1.05rem', maxWidth: '560px' }}>
          Describe your event and a swarm of specialist AI agents will craft a
          complete plan: venues, pricing, speakers, sponsors, exhibitors, and a
          go-to-market strategy.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        <h2>Event Details</h2>

        {/* Topic */}
        <div className="form-group">
          <label htmlFor="topic">Event Topic *</label>
          <input
            id="topic"
            type="text"
            placeholder="e.g. Artificial Intelligence and Machine Learning"
            value={form.topic}
            onChange={update('topic')}
            required
          />
        </div>

        {/* Domain */}
        <div className="form-group">
          <label htmlFor="domain">Event Type *</label>
          <select id="domain" value={form.domain} onChange={update('domain')}>
            {DOMAINS.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </select>
        </div>

        {/* City + Country */}
        <div className="grid-2">
          <div className="form-group">
            <label htmlFor="city">City *</label>
            <input
              id="city"
              type="text"
              placeholder="e.g. Bangalore"
              value={form.city}
              onChange={update('city')}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="country">Country *</label>
            <input
              id="country"
              type="text"
              placeholder="e.g. India"
              value={form.country}
              onChange={update('country')}
              required
            />
          </div>
        </div>

        {/* Budget + Audience */}
        <div className="grid-2">
          <div className="form-group">
            <label htmlFor="budget">Budget (USD) *</label>
            <input
              id="budget"
              type="number"
              min="1000"
              placeholder="e.g. 500000"
              value={form.budget_usd}
              onChange={update('budget_usd')}
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="audience">Target Audience *</label>
            <input
              id="audience"
              type="number"
              min="1"
              placeholder="e.g. 1000"
              value={form.target_audience}
              onChange={update('target_audience')}
              required
            />
          </div>
        </div>

        {/* Dates */}
        <div className="form-group">
          <label htmlFor="dates">Event Dates *</label>
          <input
            id="dates"
            type="text"
            placeholder="e.g. 2026-09-15 to 2026-09-17"
            value={form.dates}
            onChange={update('dates')}
            required
          />
        </div>

        {error && (
          <div style={{
            background: 'rgba(239,68,68,.12)', border: '1px solid var(--error)',
            borderRadius: 'var(--radius-sm)', padding: '.75rem 1rem', color: 'var(--error)', fontSize: '.9rem'
          }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          className="btn btn-primary"
          disabled={loading}
          style={{ alignSelf: 'flex-start', padding: '.75rem 2rem', fontSize: '1rem' }}
        >
          {loading ? 'Submitting…' : 'Generate Event Plan'}
        </button>
      </form>
    </div>
  )
}
