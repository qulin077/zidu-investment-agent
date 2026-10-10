-- 0007_production_context
-- P1.45 生产化 + P2.0 Decision Context。不改 Decision 语义，不加 Agent。

ALTER TABLE decision ADD COLUMN environment TEXT NOT NULL DEFAULT 'prod';
ALTER TABLE decision ADD COLUMN demo INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS product_event (
    id             TEXT PRIMARY KEY,
    event_type     TEXT NOT NULL,
    occurred_at    TEXT NOT NULL,
    entity_type    TEXT NOT NULL DEFAULT '',
    entity_id      TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL DEFAULT 'system',
    metadata_json  TEXT NOT NULL DEFAULT '{}',
    environment    TEXT NOT NULL DEFAULT 'prod',
    demo           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_product_event_type ON product_event(event_type, occurred_at);
CREATE INDEX IF NOT EXISTS idx_product_event_entity ON product_event(entity_type, entity_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_product_event_once
    ON product_event(event_type, entity_type, entity_id)
    WHERE event_type IN (
        'RECORDER_INPUT_RECEIVED',
        'RECORDER_DRAFT_CONFIRMED',
        'RECORDER_DRAFT_REJECTED',
        'REVIEW_COMPLETED',
        'PATTERN_CONFIRMED',
        'PATTERN_DISMISSED',
        'RULE_ACTIVATED',
        'RULE_REJECTED',
        'RULE_RETIRED'
    );

CREATE TABLE IF NOT EXISTS pipeline_run (
    id              TEXT PRIMARY KEY,
    pipeline        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'ok',
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL DEFAULT '',
    error_code      TEXT NOT NULL DEFAULT '',
    error_message   TEXT NOT NULL DEFAULT '',
    entity_ids_json TEXT NOT NULL DEFAULT '[]',
    metadata_json   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_pipe ON pipeline_run(pipeline, started_at DESC);

CREATE TABLE IF NOT EXISTS decision_context_snapshot (
    id                     TEXT PRIMARY KEY,
    decision_id            TEXT NOT NULL,
    snapshot_type          TEXT NOT NULL,
    as_of                  TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    captured_at            TEXT NOT NULL,
    context_version        TEXT NOT NULL DEFAULT 'c1',
    snapshot_version       INTEGER NOT NULL DEFAULT 1,
    market_regime          TEXT NOT NULL DEFAULT '',
    index_snapshot_json    TEXT NOT NULL DEFAULT '{}',
    sector_snapshot_json   TEXT NOT NULL DEFAULT '{}',
    breadth_snapshot_json  TEXT NOT NULL DEFAULT '{}',
    sentiment_snapshot_json TEXT NOT NULL DEFAULT '{}',
    flow_snapshot_json     TEXT NOT NULL DEFAULT '{}',
    overseas_snapshot_json TEXT NOT NULL DEFAULT '{}',
    data_freshness_json    TEXT NOT NULL DEFAULT '{}',
    data_coverage_json     TEXT NOT NULL DEFAULT '{}',
    source_refs_json       TEXT NOT NULL DEFAULT '{}',
    provider_status_json   TEXT NOT NULL DEFAULT '{}',
    coverage               TEXT NOT NULL DEFAULT 'partial',
    environment            TEXT NOT NULL DEFAULT 'prod',
    demo                   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (decision_id, snapshot_type, snapshot_version),
    CHECK (snapshot_type IN ('ENTRY_CONTEXT','REVIEW_CONTEXT')),
    CHECK (coverage IN ('full','partial'))
);
CREATE INDEX IF NOT EXISTS idx_ctx_decision ON decision_context_snapshot(decision_id, snapshot_type);

CREATE TABLE IF NOT EXISTS rule_applicability (
    rule_id        TEXT NOT NULL,
    decision_id    TEXT NOT NULL,
    applicability  TEXT NOT NULL,
    reason         TEXT NOT NULL DEFAULT '',
    computed_at    TEXT NOT NULL,
    PRIMARY KEY (rule_id, decision_id),
    CHECK (applicability IN ('APPLICABLE','NOT_APPLICABLE','UNKNOWN'))
);
CREATE INDEX IF NOT EXISTS idx_rule_app_decision ON rule_applicability(decision_id);
