-- 0018_personal_agent_context
-- Personal Agent 共享内核：策略画像、可纠正记忆、可恢复工作流和跨领域链接。
-- 行研与复盘事实仍分别保存在 research_* 与 decision/review/memory 表中。

ALTER TABLE agent_session ADD COLUMN active_strategy_id TEXT NOT NULL DEFAULT '';
ALTER TABLE research_project ADD COLUMN strategy_id TEXT NOT NULL DEFAULT '';
ALTER TABLE decision ADD COLUMN strategy_id TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS strategy_profile (
    id                         TEXT PRIMARY KEY,
    name                       TEXT NOT NULL,
    description                TEXT NOT NULL DEFAULT '',
    time_horizon               TEXT NOT NULL DEFAULT '',
    style                      TEXT NOT NULL DEFAULT '',
    status                     TEXT NOT NULL DEFAULT 'ACTIVE',
    research_preferences_json  TEXT NOT NULL DEFAULT '{}',
    decision_preferences_json  TEXT NOT NULL DEFAULT '{}',
    review_preferences_json    TEXT NOT NULL DEFAULT '{}',
    risk_constraints_json      TEXT NOT NULL DEFAULT '{}',
    created_at                 TEXT NOT NULL,
    updated_at                 TEXT NOT NULL,
    CHECK (status IN ('ACTIVE','PAUSED','ARCHIVED'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_name ON strategy_profile(name);
CREATE INDEX IF NOT EXISTS idx_strategy_status ON strategy_profile(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS personal_memory (
    id                   TEXT PRIMARY KEY,
    memory_type          TEXT NOT NULL,
    scope_type           TEXT NOT NULL DEFAULT 'GLOBAL',
    scope_id             TEXT NOT NULL DEFAULT '',
    memory_key           TEXT NOT NULL,
    value_json           TEXT NOT NULL DEFAULT '{}',
    provenance_type      TEXT NOT NULL DEFAULT 'USER',
    provenance_id        TEXT NOT NULL DEFAULT '',
    confidence           REAL NOT NULL DEFAULT 1.0,
    confirmation_status  TEXT NOT NULL DEFAULT 'EXPLICIT',
    effective_at         TEXT NOT NULL,
    superseded_by        TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    CHECK (scope_type IN ('GLOBAL','STRATEGY','INDUSTRY','COMPANY','DECISION','REVIEW')),
    CHECK (confirmation_status IN ('EXPLICIT','INFERRED','CONFIRMED','REJECTED')),
    CHECK (confidence >= 0.0 AND confidence <= 1.0)
);
CREATE INDEX IF NOT EXISTS idx_personal_memory_scope
    ON personal_memory(scope_type, scope_id, memory_key, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_personal_memory_active
    ON personal_memory(confirmation_status, superseded_by, updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_workflow (
    id                    TEXT PRIMARY KEY,
    session_id            TEXT NOT NULL,
    workflow_type         TEXT NOT NULL,
    stage                 TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'ACTIVE',
    strategy_id           TEXT NOT NULL DEFAULT '',
    industry_project_id   TEXT NOT NULL DEFAULT '',
    company_project_id    TEXT NOT NULL DEFAULT '',
    decision_id           TEXT NOT NULL DEFAULT '',
    review_id             TEXT NOT NULL DEFAULT '',
    draft_id              TEXT NOT NULL DEFAULT '',
    pending_question      TEXT NOT NULL DEFAULT '',
    state_json            TEXT NOT NULL DEFAULT '{}',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    completed_at          TEXT NOT NULL DEFAULT '',
    CHECK (status IN ('ACTIVE','COMPLETED','CANCELLED','PAUSED'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_workflow_one_active
    ON agent_workflow(session_id) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_agent_workflow_session
    ON agent_workflow(session_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_workflow_decision
    ON agent_workflow(decision_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS context_link (
    id              TEXT PRIMARY KEY,
    from_type       TEXT NOT NULL,
    from_id         TEXT NOT NULL,
    relation        TEXT NOT NULL,
    to_type         TEXT NOT NULL,
    to_id           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    source          TEXT NOT NULL DEFAULT 'system',
    user_confirmed  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    CHECK (status IN ('ACTIVE','SUPERSEDED','REJECTED')),
    CHECK (user_confirmed IN (0,1)),
    UNIQUE(from_type, from_id, relation, to_type, to_id)
);
CREATE INDEX IF NOT EXISTS idx_context_link_from
    ON context_link(from_type, from_id, relation, status);
CREATE INDEX IF NOT EXISTS idx_context_link_to
    ON context_link(to_type, to_id, relation, status);
