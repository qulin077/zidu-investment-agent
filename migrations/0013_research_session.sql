-- P3.3：研究会话、消息、可审计工作轨迹。不保存模型隐藏推理。

CREATE TABLE IF NOT EXISTS research_session (
    id                      TEXT PRIMARY KEY,
    title                   TEXT NOT NULL DEFAULT '',
    skill                   TEXT NOT NULL DEFAULT '',
    status                  TEXT NOT NULL DEFAULT 'OPEN',
    primary_entity_type     TEXT NOT NULL DEFAULT '',
    primary_entity_name     TEXT NOT NULL DEFAULT '',
    primary_entity_code     TEXT NOT NULL DEFAULT '',
    primary_entity_exchange TEXT NOT NULL DEFAULT '',
    project_id              TEXT NOT NULL DEFAULT '',
    current_thesis_id       TEXT NOT NULL DEFAULT '',
    current_thesis_version  INTEGER NOT NULL DEFAULT 0,
    summary_json            TEXT NOT NULL DEFAULT '{}',
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    last_run_id             TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS research_message (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL,
    run_id           TEXT NOT NULL DEFAULT '',
    role             TEXT NOT NULL,
    content          TEXT NOT NULL DEFAULT '',
    claim_refs_json  TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_message_session
    ON research_message(session_id, created_at);

CREATE TABLE IF NOT EXISTS research_event (
    id           TEXT PRIMARY KEY,
    seq          INTEGER NOT NULL,
    session_id   TEXT NOT NULL,
    run_id       TEXT NOT NULL DEFAULT '',
    event_type   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    UNIQUE(session_id, seq)
);

ALTER TABLE research_run ADD COLUMN session_id TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS research_source_cache (
    canonical_url TEXT PRIMARY KEY,
    content_hash  TEXT NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    publisher     TEXT NOT NULL DEFAULT '',
    published_at  TEXT NOT NULL DEFAULT '',
    content_type  TEXT NOT NULL DEFAULT '',
    text          TEXT NOT NULL DEFAULT '',
    retrieved_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_extract_cache (
    cache_key   TEXT PRIMARY KEY,
    claims_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
