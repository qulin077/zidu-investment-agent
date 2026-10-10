-- 0008_temporal_integrity
-- P2.05：cutoff / temporal policy 与 operational_error。不改 Decision 语义。

ALTER TABLE decision_context_snapshot ADD COLUMN cutoff_at TEXT NOT NULL DEFAULT '';
ALTER TABLE decision_context_snapshot ADD COLUMN temporal_policy_version TEXT NOT NULL DEFAULT '';
ALTER TABLE decision_context_snapshot ADD COLUMN temporal_coverage TEXT NOT NULL DEFAULT '';
ALTER TABLE decision_context_snapshot ADD COLUMN temporal_confidence TEXT NOT NULL DEFAULT '';
ALTER TABLE decision_context_snapshot ADD COLUMN future_rejected_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS operational_error (
    id             TEXT PRIMARY KEY,
    component      TEXT NOT NULL,
    operation      TEXT NOT NULL DEFAULT '',
    occurred_at    TEXT NOT NULL,
    error_code     TEXT NOT NULL DEFAULT '',
    error_message  TEXT NOT NULL DEFAULT '',
    entity_type    TEXT NOT NULL DEFAULT '',
    entity_id      TEXT NOT NULL DEFAULT '',
    environment    TEXT NOT NULL DEFAULT 'prod',
    resolved       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_operr_when ON operational_error(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_operr_comp ON operational_error(component, occurred_at DESC);
