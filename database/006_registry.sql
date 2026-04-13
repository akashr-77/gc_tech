-- ─── AGENT REGISTRY (persistent agent card store) ───────────────────────────
-- Replaces the in-memory dict so agent registrations survive registry restarts.
-- Agents upsert their card on startup; EventOps queries this at runtime.
CREATE TABLE IF NOT EXISTS agent_registry (
    name            TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    card            JSONB NOT NULL,
    registered_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
