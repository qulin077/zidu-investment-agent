-- 0004_recorder
-- P1.2 Recorder Agent：先见证原话，再结构化草稿，确认后才写 Decision。
-- 不删表、不改已有 execution。decision 只加 witnessed_at 与草稿外键。

ALTER TABLE decision ADD COLUMN witnessed_at TEXT NOT NULL DEFAULT '';
ALTER TABLE decision ADD COLUMN recorder_input_id TEXT NOT NULL DEFAULT '';
ALTER TABLE decision ADD COLUMN recorder_draft_id TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS recorder_input (
    id            TEXT PRIMARY KEY,
    raw_text      TEXT NOT NULL,
    received_at   TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT 'web',
    mode          TEXT NOT NULL DEFAULT '',
    known_symbol  TEXT NOT NULL DEFAULT '',
    known_company TEXT NOT NULL DEFAULT '',
    account       TEXT NOT NULL DEFAULT '',
    draft_id      TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recorder_input_received ON recorder_input(received_at);

CREATE TABLE IF NOT EXISTS recorder_draft (
    id                 TEXT PRIMARY KEY,
    input_event_id     TEXT NOT NULL REFERENCES recorder_input(id),
    raw_agent_output   TEXT NOT NULL DEFAULT '',
    parsed_json        TEXT NOT NULL DEFAULT '{}',
    validation_status  TEXT NOT NULL DEFAULT '',
    validation_errors  TEXT NOT NULL DEFAULT '[]',
    prompt_version     TEXT NOT NULL DEFAULT '',
    schema_version     TEXT NOT NULL DEFAULT '',
    model              TEXT NOT NULL DEFAULT '',
    temperature        REAL,
    created_at         TEXT NOT NULL,
    confirmed_at       TEXT NOT NULL DEFAULT '',
    confirmed_by       TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'PARSED',
    decision_id        TEXT NOT NULL DEFAULT '',
    edit_json          TEXT NOT NULL DEFAULT '',
    origin_resolved    TEXT NOT NULL DEFAULT '',
    CHECK (status IN ('PARSED','VALIDATED','NEEDS_EDIT','CONFIRMED','REJECTED','FAILED'))
);
CREATE INDEX IF NOT EXISTS idx_recorder_draft_input ON recorder_draft(input_event_id);
CREATE INDEX IF NOT EXISTS idx_recorder_draft_status ON recorder_draft(status);
