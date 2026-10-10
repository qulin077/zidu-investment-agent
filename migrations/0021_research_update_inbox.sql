-- 每日新闻只进入研究更新收件箱。标题/摘要是待核验线索，不直接写入研究结论。

CREATE TABLE IF NOT EXISTS research_update_candidate (
    id                    TEXT PRIMARY KEY,
    news_id               TEXT NOT NULL,
    news_url              TEXT NOT NULL DEFAULT '',
    news_title            TEXT NOT NULL,
    news_source           TEXT NOT NULL DEFAULT '',
    published_at          TEXT NOT NULL DEFAULT '',
    detected_at           TEXT NOT NULL,
    candidate_type        TEXT NOT NULL,
    target_type           TEXT NOT NULL,
    target_session_id     TEXT NOT NULL DEFAULT '',
    target_name           TEXT NOT NULL DEFAULT '',
    target_code           TEXT NOT NULL DEFAULT '',
    match_reason          TEXT NOT NULL DEFAULT '',
    matched_terms_json    TEXT NOT NULL DEFAULT '[]',
    importance            TEXT NOT NULL DEFAULT 'MEDIUM',
    status                TEXT NOT NULL DEFAULT 'PENDING',
    requires_user_review  INTEGER NOT NULL DEFAULT 1,
    verification_run_id   TEXT NOT NULL DEFAULT '',
    applied_at            TEXT NOT NULL DEFAULT '',
    metadata_json         TEXT NOT NULL DEFAULT '{}',
    CHECK (target_type IN ('company','industry','event','new_event')),
    CHECK (importance IN ('HIGH','MEDIUM','LOW')),
    CHECK (status IN ('PENDING','ACCEPTED','DISMISSED','VERIFIED','APPLIED','FAILED')),
    CHECK (requires_user_review IN (0,1)),
    UNIQUE(news_id, target_type, target_session_id, target_name)
);

CREATE INDEX IF NOT EXISTS idx_research_update_status
    ON research_update_candidate(status, importance, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_update_target
    ON research_update_candidate(target_session_id, status, published_at DESC);
