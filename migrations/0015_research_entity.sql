-- 0015_research_entity
-- 已核实的公司实体缓存。本地笔记没有收录时，官方检索确认后写在这里。

CREATE TABLE IF NOT EXISTS research_entity (
    id               TEXT PRIMARY KEY,
    canonical_name   TEXT NOT NULL DEFAULT '',
    ticker           TEXT NOT NULL DEFAULT '',
    exchange         TEXT NOT NULL DEFAULT '',
    aliases_json     TEXT NOT NULL DEFAULT '[]',
    entity_type      TEXT NOT NULL DEFAULT 'company',
    verified_source  TEXT NOT NULL DEFAULT '',
    verified_at      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_research_entity_name ON research_entity(canonical_name);
CREATE INDEX IF NOT EXISTS idx_research_entity_ticker ON research_entity(ticker);
