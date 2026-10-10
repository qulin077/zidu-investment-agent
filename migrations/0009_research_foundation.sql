-- 0009_research_foundation
-- P3.0：研究底稿。Decision 可以引用某版 Thesis，不强制每条 Decision 都来自研究。

ALTER TABLE decision ADD COLUMN research_project_id TEXT NOT NULL DEFAULT '';
ALTER TABLE decision ADD COLUMN research_thesis_id TEXT NOT NULL DEFAULT '';
ALTER TABLE decision ADD COLUMN research_thesis_version INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS research_project (
    id                   TEXT PRIMARY KEY,
    title                TEXT NOT NULL DEFAULT '',
    industry             TEXT NOT NULL DEFAULT '',
    scope                TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'OPEN',
    industry_definition  TEXT NOT NULL DEFAULT '',
    map_json             TEXT NOT NULL DEFAULT '{}',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    created_by           TEXT NOT NULL DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS research_question (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL REFERENCES research_project(id),
    question      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'OPEN',
    priority      INTEGER NOT NULL DEFAULT 1,
    user_context  TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    resolved_at   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS research_plan (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES research_project(id),
    run_id      TEXT NOT NULL DEFAULT '',
    steps_json  TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_source (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES research_project(id),
    url             TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL DEFAULT '',
    publisher       TEXT NOT NULL DEFAULT '',
    source_type     TEXT NOT NULL DEFAULT '',
    published_at    TEXT NOT NULL DEFAULT '',
    available_at    TEXT NOT NULL DEFAULT '',
    captured_at     TEXT NOT NULL DEFAULT '',
    author          TEXT NOT NULL DEFAULT '',
    source_quality  TEXT NOT NULL DEFAULT '',
    body            TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS research_claim (
    id                 TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL REFERENCES research_project(id),
    local_id           TEXT NOT NULL DEFAULT '',
    claim_text         TEXT NOT NULL DEFAULT '',
    claim_type         TEXT NOT NULL,
    subject            TEXT NOT NULL DEFAULT '',
    predicate          TEXT NOT NULL DEFAULT '',
    object             TEXT NOT NULL DEFAULT '',
    unit               TEXT NOT NULL DEFAULT '',
    period             TEXT NOT NULL DEFAULT '',
    confidence         TEXT NOT NULL DEFAULT 'LOW',
    status             TEXT NOT NULL DEFAULT 'SINGLE_SOURCE',
    critical           INTEGER NOT NULL DEFAULT 0,
    metric             TEXT NOT NULL DEFAULT '',
    numeric_value      REAL,
    definition         TEXT NOT NULL DEFAULT '',
    premise_claim_ids  TEXT NOT NULL DEFAULT '[]',
    created_at         TEXT NOT NULL,
    CHECK (claim_type IN ('FACT','ESTIMATE','INFERENCE','OPINION')),
    CHECK (status IN ('SINGLE_SOURCE','CORROBORATED','CONTESTED','SUPERSEDED','REJECTED'))
);

CREATE TABLE IF NOT EXISTS research_evidence (
    id                 TEXT PRIMARY KEY,
    claim_id           TEXT NOT NULL REFERENCES research_claim(id),
    source_id          TEXT NOT NULL REFERENCES research_source(id),
    evidence_text      TEXT NOT NULL DEFAULT '',
    evidence_location  TEXT NOT NULL DEFAULT '',
    support_type       TEXT NOT NULL DEFAULT 'SUPPORT',
    captured_at        TEXT NOT NULL DEFAULT '',
    CHECK (support_type IN ('SUPPORT','CONTRADICT','CONTEXT'))
);

CREATE TABLE IF NOT EXISTS research_conflict (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL REFERENCES research_project(id),
    metric           TEXT NOT NULL DEFAULT '',
    value_a          TEXT NOT NULL DEFAULT '',
    definition_a     TEXT NOT NULL DEFAULT '',
    value_b          TEXT NOT NULL DEFAULT '',
    definition_b     TEXT NOT NULL DEFAULT '',
    possible_reason  TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'OPEN',
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_value_chain (
    id                    TEXT PRIMARY KEY,
    project_id            TEXT NOT NULL REFERENCES research_project(id),
    node_name             TEXT NOT NULL,
    upstream_node         TEXT NOT NULL DEFAULT '',
    downstream_node       TEXT NOT NULL DEFAULT '',
    role                  TEXT NOT NULL DEFAULT '',
    value_driver          TEXT NOT NULL DEFAULT '',
    margin_characteristic TEXT NOT NULL DEFAULT 'UNKNOWN',
    bottleneck            TEXT NOT NULL DEFAULT 'UNKNOWN'
);

CREATE TABLE IF NOT EXISTS research_company_mapping (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES research_project(id),
    company             TEXT NOT NULL DEFAULT '',
    code                TEXT NOT NULL DEFAULT '',
    value_chain_node    TEXT NOT NULL DEFAULT '',
    exposure_type       TEXT NOT NULL DEFAULT 'UNKNOWN',
    evidence_level      TEXT NOT NULL DEFAULT 'NONE',
    revenue_exposure    TEXT NOT NULL DEFAULT 'UNKNOWN',
    customer_evidence   TEXT NOT NULL DEFAULT '',
    product_evidence    TEXT NOT NULL DEFAULT '',
    confidence          TEXT NOT NULL DEFAULT 'LOW',
    evidence_refs       TEXT NOT NULL DEFAULT '[]',
    CHECK (exposure_type IN ('DIRECT','INDIRECT','THEMATIC','UNKNOWN'))
);

CREATE TABLE IF NOT EXISTS research_open_question (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES research_project(id),
    thesis_version  INTEGER NOT NULL DEFAULT 1,
    question        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'OPEN',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_thesis (
    id                   TEXT NOT NULL,
    project_id           TEXT NOT NULL REFERENCES research_project(id),
    version              INTEGER NOT NULL,
    summary              TEXT NOT NULL DEFAULT '',
    bull_case            TEXT NOT NULL DEFAULT '',
    base_case            TEXT NOT NULL DEFAULT '',
    bear_case            TEXT NOT NULL DEFAULT '',
    key_drivers_json     TEXT NOT NULL DEFAULT '[]',
    catalysts_json       TEXT NOT NULL DEFAULT '[]',
    risks_json           TEXT NOT NULL DEFAULT '[]',
    invalidation         TEXT NOT NULL DEFAULT '',
    open_questions_json  TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json   TEXT NOT NULL DEFAULT '[]',
    map_json             TEXT NOT NULL DEFAULT '{}',
    diff_verdict         TEXT NOT NULL DEFAULT '',
    diff_json            TEXT NOT NULL DEFAULT '{}',
    as_of                TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'SAVED',
    created_at           TEXT NOT NULL,
    PRIMARY KEY (id, version)
);

CREATE TABLE IF NOT EXISTS research_run (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL DEFAULT '',
    skill             TEXT NOT NULL DEFAULT '',
    question          TEXT NOT NULL DEFAULT '',
    started_at        TEXT NOT NULL,
    finished_at       TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'running',
    mode              TEXT NOT NULL DEFAULT '',
    model             TEXT NOT NULL DEFAULT '',
    prompt_versions   TEXT NOT NULL DEFAULT '{}',
    temperature       REAL,
    tool_calls        INTEGER NOT NULL DEFAULT 0,
    tool_log_json     TEXT NOT NULL DEFAULT '[]',
    llm_calls         INTEGER NOT NULL DEFAULT 0,
    tokens            INTEGER,
    cost              REAL,
    error_code        TEXT NOT NULL DEFAULT '',
    error_message     TEXT NOT NULL DEFAULT '',
    raw_output        TEXT NOT NULL DEFAULT '',
    parsed_output     TEXT NOT NULL DEFAULT '',
    plan_json         TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_rq_project ON research_question(project_id);
CREATE INDEX IF NOT EXISTS idx_rs_project ON research_source(project_id);
CREATE INDEX IF NOT EXISTS idx_rc_project ON research_claim(project_id);
CREATE INDEX IF NOT EXISTS idx_rthesis_project ON research_thesis(project_id, version);
CREATE INDEX IF NOT EXISTS idx_rrun_project ON research_run(project_id);
