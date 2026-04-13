-- ─── REACTIVE EVENTS (EventOps trigger queue) ────────────────────────────────
-- Used by ReactiveMonitor to queue and process events during a planning session.
CREATE TABLE IF NOT EXISTS reactive_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,        -- 'user_request', 'agent_update', 'conflict', etc.
    source      TEXT DEFAULT 'system',
    payload     JSONB DEFAULT '{}',
    processed   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_re_session     ON reactive_events (session_id);
CREATE INDEX IF NOT EXISTS idx_re_unprocessed ON reactive_events (session_id, processed)
    WHERE processed = FALSE;

-- ─── ORCHESTRATION CHECKPOINTS (crash-resilient orchestration state) ─────────
-- Stores full orchestration state after each step so EventOps can resume
-- from the last checkpoint after a crash or restart.
CREATE TABLE IF NOT EXISTS orchestration_checkpoints (
    session_id        TEXT PRIMARY KEY,
    event_input       JSONB,
    task_plan         JSONB,
    completed_agents  JSONB DEFAULT '[]',
    agent_outputs     JSONB DEFAULT '{}',
    conflicts         JSONB DEFAULT '[]',
    final_plan        JSONB,
    status            TEXT  DEFAULT 'planning',
                      -- planning, executing, compiling, completed, failed, monitoring
    current_agent     TEXT,
    error_message     TEXT,
    monitor_active    BOOLEAN DEFAULT FALSE,
    monitor_cycle     INT     DEFAULT 0,
    started_at        TIMESTAMPTZ DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_oc_status ON orchestration_checkpoints (status);
