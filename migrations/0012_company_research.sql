-- P3.25：预期分层。财务快照留在项目 map_json，不另建宽表。

CREATE TABLE IF NOT EXISTS research_expectation (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    statement    TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
