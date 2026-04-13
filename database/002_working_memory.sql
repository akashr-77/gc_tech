-- ─── WORKING MEMORY (session-scoped context) ─────────────────────────────────
-- Short-lived, session-keyed key/value store for agent context sharing.
-- Agents write context during a session; other agents in the same session can read it.
CREATE TABLE IF NOT EXISTS working_memory (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  TEXT NOT NULL,
    agent_name  TEXT NOT NULL,
    key         TEXT NOT NULL,         -- e.g., 'venue_shortlist', 'budget_envelope'
    value       JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, agent_name, key)
);
CREATE INDEX IF NOT EXISTS idx_wm_session ON working_memory (session_id);
CREATE INDEX IF NOT EXISTS idx_wm_session_agent ON working_memory (session_id, agent_name);


