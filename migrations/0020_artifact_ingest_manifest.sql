-- 0020_artifact_ingest_manifest
-- SQLite 是结构化事实源；Artifact 可重建；文件/远端采集有可追溯 manifest。

ALTER TABLE artifact ADD COLUMN truth_source TEXT NOT NULL DEFAULT 'DERIVED';
ALTER TABLE artifact ADD COLUMN built_from_json TEXT NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS ingest_manifest (
    id             TEXT PRIMARY KEY,
    dataset        TEXT NOT NULL,
    source_uri     TEXT NOT NULL,
    source_kind    TEXT NOT NULL DEFAULT 'FILE',
    content_hash   TEXT NOT NULL DEFAULT '',
    as_of          TEXT NOT NULL DEFAULT '',
    ingested_at    TEXT NOT NULL,
    target_table   TEXT NOT NULL DEFAULT '',
    rows_written   INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'INGESTED',
    message        TEXT NOT NULL DEFAULT '',
    CHECK (status IN ('INGESTED','SKIPPED','FAILED','STALE')),
    UNIQUE(dataset, source_uri, content_hash, ingested_at)
);
CREATE INDEX IF NOT EXISTS idx_ingest_manifest_dataset
    ON ingest_manifest(dataset, ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingest_manifest_source
    ON ingest_manifest(source_uri, ingested_at DESC);
