-- ─── PROCEDURAL MEMORY (The Rulebook) ────────────────────────────────────────
-- Hard business rules, compliance constraints, and SOPs that agents must follow.
-- Agents query this via the "query_guidelines_and_rules" MCP tool.
CREATE TABLE IF NOT EXISTS procedural_rules (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    topic       TEXT NOT NULL,            -- 'gdpr', 'medical_compliance', 'budget', 'sponsorship', etc.
    region      TEXT,                     -- 'europe', 'us', 'india', 'global' (NULL = applies everywhere)
    domain      TEXT,                     -- 'conference', 'music_festival', 'sporting_event' (NULL = all)
    rule_text   TEXT NOT NULL,            -- Human-readable rule description
    severity    TEXT DEFAULT 'warning',   -- 'info', 'warning', 'critical' (critical = must follow)
    source      TEXT,                     -- Where this rule came from: 'GDPR Article 6', 'Internal SOP', etc.
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pr_topic ON procedural_rules (topic);
CREATE INDEX IF NOT EXISTS idx_pr_region ON procedural_rules (region);
CREATE INDEX IF NOT EXISTS idx_pr_domain ON procedural_rules (domain);
