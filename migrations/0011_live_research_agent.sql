-- P3.2：来源家族、反证、Claim 关系和正文切片。不建向量库。

ALTER TABLE research_source ADD COLUMN origin_family TEXT NOT NULL DEFAULT '';
ALTER TABLE research_company_mapping ADD COLUMN commercial_stage TEXT NOT NULL DEFAULT 'UNKNOWN';

CREATE TABLE IF NOT EXISTS research_disconfirmation (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    claim_id    TEXT NOT NULL DEFAULT '',
    query       TEXT NOT NULL DEFAULT '',
    source_ids  TEXT NOT NULL DEFAULT '[]',
    result      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_claim_relation (
    id               TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    source_claim_id  TEXT NOT NULL,
    target_claim_id  TEXT NOT NULL,
    relation         TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_source_chunk (
    id          TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,
    section     TEXT NOT NULL DEFAULT '',
    page_start  INTEGER,
    page_end    INTEGER,
    ordinal     INTEGER NOT NULL DEFAULT 0,
    text        TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS research_source_fts USING fts5(
    source_id UNINDEXED,
    section,
    body
);
