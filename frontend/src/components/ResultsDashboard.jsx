import { useState } from 'react'

// ─── Utility helpers ──────────────────────────────────────────────────────────

function fmt(val) {
  if (val == null) return '—'
  if (typeof val === 'number') return val.toLocaleString()
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  return String(val)
}

function fmtUSD(num) {
  if (!num && num !== 0) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(num)
}

// ─── Collapsible section ──────────────────────────────────────────────────────

function Section({ title, icon, badge, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{ marginBottom: '.75rem' }}>
      <div
        className={`section-header${open ? ' open' : ''}`}
        onClick={() => setOpen(!open)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem' }}>
          <span>{icon}</span>
          <h3 style={{ margin: 0 }}>{title}</h3>
          {badge != null && (
            <span className="tag">{badge}</span>
          )}
        </div>
        <span className={`chevron${open ? ' open' : ''}`}>▶</span>
      </div>
      {open && <div className="section-body">{children}</div>}
    </div>
  )
}

// ─── KV grid ──────────────────────────────────────────────────────────────────

function KVGrid({ data, cols = 3 }) {
  const entries = Object.entries(data).filter(([, v]) => v != null)
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: '.75rem' }}>
      {entries.map(([k, v]) => (
        <div key={k} style={{ background: 'var(--bg)', borderRadius: 'var(--radius-sm)', padding: '.6rem .85rem' }}>
          <div className="text-sm text-muted" style={{ textTransform: 'capitalize', marginBottom: '.15rem' }}>
            {k.replace(/_/g, ' ')}
          </div>
          <div className="bold" style={{ wordBreak: 'break-word' }}>{fmt(v)}</div>
        </div>
      ))}
    </div>
  )
}

// ─── Venue section ────────────────────────────────────────────────────────────

function VenueSection({ venues }) {
  if (!venues?.length) return <p className="text-muted">No venue data available.</p>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {venues.map((v, i) => (
        <div key={i} className="card-sm">
          <div className="flex-between mb-1">
            <h4>{v.name || `Venue ${i + 1}`}</h4>
            {v.recommended && <span className="tag" style={{ background: 'rgba(16,185,129,.15)', color: 'var(--success)' }}>⭐ Recommended</span>}
          </div>
          <div className="grid-2" style={{ fontSize: '.88rem' }}>
            {v.location    && <div><span className="text-muted">Location: </span>{v.location}</div>}
            {v.capacity    && <div><span className="text-muted">Capacity: </span>{fmt(v.capacity)}</div>}
            {v.price_per_day_usd && <div><span className="text-muted">Price/day: </span>{fmtUSD(v.price_per_day_usd)}</div>}
            {v.total_cost_usd    && <div><span className="text-muted">Total cost: </span>{fmtUSD(v.total_cost_usd)}</div>}
          </div>
          {v.amenities?.length > 0 && (
            <div className="mt-1" style={{ display: 'flex', flexWrap: 'wrap', gap: '.35rem' }}>
              {v.amenities.map((a, j) => <span key={j} className="tag">{a}</span>)}
            </div>
          )}
          {v.notes && <p className="text-sm mt-1">{v.notes}</p>}
        </div>
      ))}
    </div>
  )
}

// ─── Pricing section ──────────────────────────────────────────────────────────

function PricingSection({ tiers, forecastUSD }) {
  return (
    <div>
      {forecastUSD != null && (
        <div style={{ background: 'rgba(16,185,129,.1)', border: '1px solid rgba(16,185,129,.3)', borderRadius: 'var(--radius-sm)', padding: '.75rem 1rem', marginBottom: '1rem' }}>
          <span className="text-muted text-sm">Revenue Forecast: </span>
          <span className="bold text-success" style={{ fontSize: '1.2rem' }}>{fmtUSD(forecastUSD)}</span>
        </div>
      )}
      {tiers?.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Tier</th>
              <th>Price (USD)</th>
              <th>Expected Sales</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {tiers.map((t, i) => (
              <tr key={i}>
                <td className="bold">{t.tier || t.name || `Tier ${i+1}`}</td>
                <td>{fmtUSD(t.price_usd ?? t.price)}</td>
                <td>{fmt(t.expected_sales ?? t.quantity)}</td>
                <td className="text-muted" style={{ fontSize: '.85rem' }}>{t.description || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-muted">No pricing data available.</p>
      )}
    </div>
  )
}

// ─── Speakers section ─────────────────────────────────────────────────────────

function SpeakersSection({ speakers }) {
  if (!speakers?.length) return <p className="text-muted">No speaker data available.</p>
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
      {speakers.map((s, i) => (
        <div key={i} className="card-sm">
          <h4 style={{ marginBottom: '.25rem' }}>{s.name || `Speaker ${i+1}`}</h4>
          {s.title    && <p className="text-sm text-muted">{s.title}</p>}
          {s.company  && <p className="text-sm text-muted">{s.company}</p>}
          {s.topic    && <p className="text-sm mt-1"><span className="text-muted">Topic: </span>{s.topic}</p>}
          {s.bio      && <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>{s.bio.substring(0, 160)}{s.bio.length > 160 ? '…' : ''}</p>}
        </div>
      ))}
    </div>
  )
}

// ─── Schedule section ─────────────────────────────────────────────────────────

function ScheduleSection({ schedule }) {
  if (!schedule) return <p className="text-muted">No schedule data available.</p>

  const grid      = schedule.schedule_grid || schedule.grid || []
  const conflicts = schedule.conflicts || []

  if (!grid.length) {
    return <pre style={{ fontSize: '.82rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-muted)' }}>{JSON.stringify(schedule, null, 2)}</pre>
  }

  return (
    <div>
      {conflicts.length > 0 && (
        <div style={{ background: 'rgba(245,158,11,.1)', border: '1px solid rgba(245,158,11,.3)', borderRadius: 'var(--radius-sm)', padding: '.75rem 1rem', marginBottom: '1rem' }}>
          <span className="text-warn bold">⚠️ {conflicts.length} conflict(s) detected</span>
          <ul style={{ marginTop: '.35rem', paddingLeft: '1.2rem', fontSize: '.85rem', color: 'var(--text-muted)' }}>
            {conflicts.map((c, i) => <li key={i}>{typeof c === 'string' ? c : JSON.stringify(c)}</li>)}
          </ul>
        </div>
      )}
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              {Object.keys(grid[0] || {}).map(k => <th key={k}>{k.replace(/_/g, ' ')}</th>)}
            </tr>
          </thead>
          <tbody>
            {grid.map((row, i) => (
              <tr key={i}>
                {Object.values(row).map((v, j) => <td key={j}>{fmt(v)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── Sponsors section ─────────────────────────────────────────────────────────

function SponsorsSection({ sponsors }) {
  if (!sponsors?.length) return <p className="text-muted">No sponsor data available.</p>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '.75rem' }}>
      {sponsors.map((s, i) => (
        <div key={i} className="card-sm">
          <div className="flex-between">
            <h4>{s.company_name || s.name || s.company || `Sponsor ${i+1}`}</h4>
            {s.tier     && <span className="tag">{s.tier}</span>}
            {s.amount_usd && <span className="bold text-success">{fmtUSD(s.amount_usd)}</span>}
          </div>
          {s.industry   && <p className="text-sm text-muted mt-1">{s.industry}</p>}
          {s.proposal   && <p className="text-sm mt-1">{s.proposal}</p>}
          {s.contact    && <p className="text-sm text-muted mt-1">Contact: {s.contact}</p>}
        </div>
      ))}
    </div>
  )
}

// ─── Exhibitors section ───────────────────────────────────────────────────────

function ExhibitorsSection({ exhibitors }) {
  if (!exhibitors?.length) return <p className="text-muted">No exhibitor data available.</p>
  return (
    <table>
      <thead>
        <tr>
          <th>Company / Name</th>
          <th>Booth</th>
          <th>Category</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
        {exhibitors.map((e, i) => (
          <tr key={i}>
            <td className="bold">{e.company_name || e.name || e.company || `Exhibitor ${i+1}`}</td>
            <td>{e.booth_number || e.booth || '—'}</td>
            <td>{e.category || e.industry || '—'}</td>
            <td className="text-muted" style={{ fontSize: '.85rem' }}>{e.notes || e.description || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ─── Community / GTM section ──────────────────────────────────────────────────

function CommunitySection({ strategy }) {
  if (!strategy) return <p className="text-muted">No community strategy available.</p>

  const renderValue = (val, depth = 0) => {
    if (val == null) return '—'
    if (typeof val === 'string' || typeof val === 'number') return <span>{String(val)}</span>
    if (Array.isArray(val)) {
      return (
        <ul style={{ paddingLeft: '1.1rem', marginTop: '.25rem' }}>
          {val.map((item, i) => <li key={i} style={{ marginBottom: '.2rem' }}>{renderValue(item, depth + 1)}</li>)}
        </ul>
      )
    }
    if (typeof val === 'object') {
      return (
        <div style={{ marginTop: depth ? '.5rem' : 0 }}>
          {Object.entries(val).map(([k, v]) => (
            <div key={k} style={{ marginBottom: '.6rem' }}>
              <div className="bold text-sm" style={{ textTransform: 'capitalize', color: 'var(--text)', marginBottom: '.15rem' }}>
                {k.replace(/_/g, ' ')}
              </div>
              <div className="text-muted" style={{ fontSize: '.9rem' }}>{renderValue(v, depth + 1)}</div>
            </div>
          ))}
        </div>
      )
    }
    return <span>{JSON.stringify(val)}</span>
  }

  return <div style={{ fontSize: '.9rem' }}>{renderValue(strategy)}</div>
}

// ─── Main Results Dashboard ───────────────────────────────────────────────────

export default function ResultsDashboard({ sessionId, sessionData, onBack }) {
  if (!sessionData) {
    return (
      <div className="card">
        <p className="text-muted">No session data to display.</p>
        <button className="btn btn-outline mt-2" onClick={onBack}>← Back</button>
      </div>
    )
  }

  const { status, input, final_plan, error, started_at, completed_at } = sessionData

  // Normalise plan — it might be a JSON string or already an object
  let plan = final_plan
  if (typeof plan === 'string') {
    try { plan = JSON.parse(plan) } catch (e) { console.error('Failed to parse final_plan JSON:', e) }
  }

  const details = plan?.event_details ?? input ?? {}

  return (
    <div>
      {/* Header */}
      <div className="flex-between mb-2" style={{ marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '.75rem', marginBottom: '.35rem' }}>
            <h2 style={{ margin: 0 }}>{details.topic || 'Event Plan'}</h2>
            <span className={`badge badge-${status}`}>{status}</span>
          </div>
          <p className="text-sm text-muted">
            {details.city && `${details.city}, `}{details.country}
            {details.dates && ` · ${details.dates}`}
            {started_at && ` · Started ${new Date(started_at).toLocaleString()}`}
          </p>
        </div>
        <button className="btn btn-outline" onClick={onBack}>← New Plan</button>
      </div>

      {/* Error state */}
      {status === 'failed' && (
        <div className="card" style={{ borderColor: 'var(--error)', marginBottom: '1rem' }}>
          <h3 className="text-error mb-1">Planning failed</h3>
          <p className="text-sm">{error || 'Unknown error'}</p>
        </div>
      )}

      {/* Summary stats */}
      {plan && typeof plan === 'object' && (
        <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
          {[
            { label: 'Budget',          value: fmtUSD(details.budget_usd) },
            { label: 'Target Audience', value: fmt(details.target_audience) },
            { label: 'Revenue Forecast',value: fmtUSD(plan.revenue_forecast_usd) },
            { label: 'Venues Sourced',  value: fmt(plan.venue_options?.length) },
            { label: 'Speakers',        value: fmt(plan.speakers?.length) },
            { label: 'Sponsors',        value: fmt(plan.sponsors?.length) },
          ].map((stat, i) => (
            <div key={i} className="card-sm" style={{ textAlign: 'center' }}>
              <div className="text-muted text-sm">{stat.label}</div>
              <div className="bold" style={{ fontSize: '1.25rem', marginTop: '.25rem' }}>{stat.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* If plan is still a raw string, just show it */}
      {typeof plan === 'string' && (
        <div className="card">
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: '.85rem', color: 'var(--text-muted)' }}>{plan}</pre>
        </div>
      )}

      {/* Accordion sections */}
      {plan && typeof plan === 'object' && (
        <div>
          <Section title="Event Details"        icon="📌" defaultOpen={true}>
            <KVGrid data={details} cols={3} />
          </Section>

          <Section title="Venues"               icon="🏛️" badge={plan.venue_options?.length}>
            <VenueSection venues={plan.venue_options} />
          </Section>

          <Section title="Ticket Pricing"       icon="💰" badge={plan.ticket_pricing_tiers?.length}>
            <PricingSection tiers={plan.ticket_pricing_tiers} forecastUSD={plan.revenue_forecast_usd} />
          </Section>

          <Section title="Speakers"             icon="🎤" badge={plan.speakers?.length}>
            <SpeakersSection speakers={plan.speakers} />
          </Section>

          <Section title="Event Schedule"       icon="📅">
            <ScheduleSection schedule={plan.schedule} />
          </Section>

          <Section title="Sponsors"             icon="🤝" badge={plan.sponsors?.length}>
            <SponsorsSection sponsors={plan.sponsors} />
          </Section>

          <Section title="Exhibitors"           icon="🗺️" badge={plan.exhibitors?.length}>
            <ExhibitorsSection exhibitors={plan.exhibitors} />
          </Section>

          <Section title="Community & GTM Strategy" icon="📣">
            <CommunitySection strategy={plan.community_gtm_strategy} />
          </Section>
        </div>
      )}

      {/* Footer */}
      {completed_at && (
        <p className="text-sm text-muted mt-2" style={{ textAlign: 'center', marginTop: '2rem' }}>
          Plan completed at {new Date(completed_at).toLocaleString()}
        </p>
      )}
    </div>
  )
}
