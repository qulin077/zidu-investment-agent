-- 0014_investment_agent
-- P4.0：主对话、执行轨迹、Artifact 视图、轻量 Goal。
-- 不替代 research_*、decision、pattern、rule。
-- background_job 只占位。这一版不插入、不调度。

CREATE TABLE IF NOT EXISTS agent_session (
    id                 TEXT PRIMARY KEY,
    title              TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'OPEN',
    active_goal_id     TEXT NOT NULL DEFAULT '',
    active_project_id  TEXT NOT NULL DEFAULT '',
    active_decision_id TEXT NOT NULL DEFAULT '',
    current_domain     TEXT NOT NULL DEFAULT 'GENERAL',
    summary_json       TEXT NOT NULL DEFAULT '{}',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    CHECK (current_domain IN ('RESEARCH', 'DECISION', 'REVIEW', 'GENERAL'))
);

CREATE TABLE IF NOT EXISTS agent_message (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    role                TEXT NOT NULL,
    content             TEXT NOT NULL,
    domain              TEXT NOT NULL DEFAULT 'GENERAL',
    skill               TEXT NOT NULL DEFAULT '',
    entity_refs_json    TEXT NOT NULL DEFAULT '[]',
    project_refs_json   TEXT NOT NULL DEFAULT '[]',
    decision_refs_json  TEXT NOT NULL DEFAULT '[]',
    claim_refs_json     TEXT NOT NULL DEFAULT '[]',
    source_refs_json    TEXT NOT NULL DEFAULT '[]',
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_message_session ON agent_message(session_id, created_at);

CREATE TABLE IF NOT EXISTS agent_activity (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL DEFAULT '',
    project_id    TEXT NOT NULL DEFAULT '',
    decision_id   TEXT NOT NULL DEFAULT '',
    run_id        TEXT NOT NULL DEFAULT '',
    type          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'ok',
    summary       TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_activity_session ON agent_activity(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_activity_project ON agent_activity(project_id, created_at);

CREATE TABLE IF NOT EXISTS artifact (
    id           TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    project_id   TEXT NOT NULL DEFAULT '',
    decision_id  TEXT NOT NULL DEFAULT '',
    version      INTEGER NOT NULL DEFAULT 1,
    data_json    TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifact_project ON artifact(project_id, type, version);

CREATE TABLE IF NOT EXISTS agent_goal (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    goal_type     TEXT NOT NULL DEFAULT 'GENERAL',
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    description   TEXT NOT NULL DEFAULT '',
    progress_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    CHECK (goal_type IN ('RESEARCH', 'BEHAVIOR', 'GENERAL'))
);

CREATE TABLE IF NOT EXISTS background_job (
    id           TEXT PRIMARY KEY,
    job_type     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'RESERVED',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL
);
