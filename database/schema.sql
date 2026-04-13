CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── EPISODIC MEMORY (pgvector) ───────────────────────────────────────────────
CREATE TABLE agent_memories (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    namespace   TEXT NOT NULL,        -- 'venue_agent', 'sponsor_agent', etc.
    content     TEXT NOT NULL,        -- human-readable text that was embedded
    embedding   vector(1536),         -- text-embedding-3-small output
    metadata    JSONB DEFAULT '{}',   -- {type, entity_id, domain, geography, ...}
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON agent_memories USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
CREATE INDEX ON agent_memories (namespace);

-- ─── STRUCTURED / PROCEDURAL DATA ────────────────────────────────────────────
CREATE TABLE events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    domain          TEXT NOT NULL,    -- 'conference', 'music_festival', 'sporting_event'
    topic           TEXT,
    geography       TEXT,
    city            TEXT,
    country         TEXT,
    start_date      DATE,
    end_date        DATE,
    budget_usd      BIGINT,
    target_audience INT,
    website         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE venues (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    city            TEXT NOT NULL,
    country         TEXT NOT NULL,
    address         TEXT,
    capacity_min    INT,
    capacity_max    INT,
    price_per_day   BIGINT,
    currency        TEXT DEFAULT 'USD',
    amenities       TEXT[],
    past_events     TEXT[],
    website         TEXT,
    source          TEXT,             -- 'cvent', 'eventlocations', 'manual'
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sponsors (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company         TEXT NOT NULL,
    industry        TEXT,
    geography       TEXT[],
    website         TEXT,
    marketing_spend TEXT,             -- 'low', 'medium', 'high', 'enterprise'
    tier_preference TEXT,             -- 'title', 'gold', 'silver', 'bronze'
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sponsor_history (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sponsor_id  UUID REFERENCES sponsors(id),
    event_name  TEXT,
    event_domain TEXT,
    event_date  DATE,
    geography   TEXT,
    tier        TEXT,
    amount_usd  BIGINT,
    outcome     TEXT                  -- 'renewed', 'one-time', 'declined-renewal'
);

CREATE TABLE speakers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    bio             TEXT,
    topics          TEXT[],
    linkedin_url    TEXT,
    twitter_handle  TEXT,
    follower_count  INT,
    publications    INT DEFAULT 0,
    past_events     TEXT[],
    geography       TEXT,
    fee_range       TEXT,             -- 'free', 'low', 'medium', 'high', 'keynote'
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE exhibitors (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company         TEXT NOT NULL,
    category        TEXT,             -- 'startup', 'enterprise', 'tools', 'individual'
    industry        TEXT,
    geography       TEXT[],
    past_events     TEXT[],
    booth_size_pref TEXT,
    website         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE communities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    platform        TEXT NOT NULL,    -- 'discord', 'slack', 'linkedin', 'facebook'
    niche           TEXT,
    member_count    INT,
    geography       TEXT,
    join_url        TEXT,
    activity_level  TEXT,             -- 'high', 'medium', 'low'
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pricing_models (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_domain    TEXT,
    geography       TEXT,
    audience_size   INT,
    early_bird_usd  INT,
    regular_usd     INT,
    vip_usd         INT,
    conversion_rate FLOAT,
    historical_ref  TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── A2A TASK TRACKING ────────────────────────────────────────────────────────
CREATE TABLE agent_tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      TEXT NOT NULL,
    agent_name      TEXT NOT NULL,
    task_type       TEXT,
    status          TEXT DEFAULT 'submitted',
                    -- submitted, working, input_required, completed, failed, canceled
    input_data      JSONB,
    output_data     JSONB,
    confidence      FLOAT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX ON agent_tasks (session_id);
CREATE INDEX ON agent_tasks (status);
