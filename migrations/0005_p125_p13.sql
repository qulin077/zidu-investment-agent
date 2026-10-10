-- 0005_p125_p13
-- P1.25：origin 在首笔关联成交时才结算；shadow 对照。
-- P1.3：Guided Review 会话 / 轮次 / attribution 草稿。不改 execution。

ALTER TABLE decision ADD COLUMN origin_status TEXT NOT NULL DEFAULT 'SETTLED';
ALTER TABLE decision ADD COLUMN origin_confidence TEXT NOT NULL DEFAULT 'KNOWN';

CREATE TABLE IF NOT EXISTS recorder_shadow (
    id                         TEXT PRIMARY KEY,
    input_event_id             TEXT NOT NULL,
    primary_draft_id           TEXT NOT NULL DEFAULT '',
    model                      TEXT NOT NULL DEFAULT '',
    raw_agent_output           TEXT NOT NULL DEFAULT '',
    parsed_json                TEXT NOT NULL DEFAULT '{}',
    same_fields                TEXT NOT NULL DEFAULT '[]',
    different_fields           TEXT NOT NULL DEFAULT '[]',
    critical_differences       TEXT NOT NULL DEFAULT '[]',
    shadow_grounding_failures  TEXT NOT NULL DEFAULT '[]',
    created_at                 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recorder_shadow_input ON recorder_shadow(input_event_id);

CREATE TABLE IF NOT EXISTS guided_review_session (
    id                 TEXT PRIMARY KEY,
    decision_id        TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'OPEN',
    prompt_version     TEXT NOT NULL DEFAULT 'gr1',
    model              TEXT NOT NULL DEFAULT '',
    context_hash       TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    confirmed_at       TEXT NOT NULL DEFAULT '',
    review_id          TEXT NOT NULL DEFAULT '',
    CHECK (status IN ('OPEN','WAITING_USER','DRAFT','CONFIRMED','REJECTED'))
);
CREATE INDEX IF NOT EXISTS idx_guided_session_decision ON guided_review_session(decision_id);

CREATE TABLE IF NOT EXISTS guided_review_turn (
    id                 TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL,
    turn_index         INTEGER NOT NULL,
    unresolved         TEXT NOT NULL DEFAULT '',
    question           TEXT NOT NULL DEFAULT '',
    raw_agent_output   TEXT NOT NULL DEFAULT '',
    parsed_json        TEXT NOT NULL DEFAULT '{}',
    user_answer        TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    answered_at        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_guided_turn_session ON guided_review_turn(session_id);

CREATE TABLE IF NOT EXISTS attribution_draft (
    id                 TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL,
    decision_id        TEXT NOT NULL,
    parsed_json        TEXT NOT NULL DEFAULT '{}',
    primary_error      TEXT NOT NULL DEFAULT '',
    evidence           TEXT NOT NULL DEFAULT '[]',
    user_confirmed     INTEGER NOT NULL DEFAULT 0,
    confirmed_at       TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attr_draft_decision ON attribution_draft(decision_id);
