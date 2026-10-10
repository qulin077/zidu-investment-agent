-- 0019_review_research_feedback
-- 复盘可以提出研究反馈，但不能直接改 Claim / Thesis。

CREATE TABLE IF NOT EXISTS research_feedback_candidate (
    id                       TEXT PRIMARY KEY,
    decision_id              TEXT NOT NULL,
    review_id                TEXT NOT NULL DEFAULT '',
    research_project_id      TEXT NOT NULL DEFAULT '',
    research_thesis_id       TEXT NOT NULL DEFAULT '',
    research_thesis_version  INTEGER NOT NULL DEFAULT 0,
    feedback_type            TEXT NOT NULL,
    statement                TEXT NOT NULL DEFAULT '',
    evidence_json            TEXT NOT NULL DEFAULT '[]',
    status                   TEXT NOT NULL DEFAULT 'PROPOSED',
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    applied_at               TEXT NOT NULL DEFAULT '',
    CHECK (status IN ('PROPOSED','CONFIRMED','REJECTED','APPLIED')),
    UNIQUE(decision_id, feedback_type, research_thesis_id, research_thesis_version)
);
CREATE INDEX IF NOT EXISTS idx_research_feedback_project
    ON research_feedback_candidate(research_project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_feedback_decision
    ON research_feedback_candidate(decision_id, status, created_at DESC);
