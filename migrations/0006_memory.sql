-- 0006_memory
-- P1.4：Mistake / Pattern / Rule。Lesson 不自动变 Rule。
-- 只吃 REVIEWED + user_confirmed attribution。Process Violation ≠ Mistake。

CREATE TABLE IF NOT EXISTS mistake_instance (
    id                   TEXT PRIMARY KEY,
    decision_id          TEXT NOT NULL UNIQUE,
    primary_error        TEXT NOT NULL,
    contributing         TEXT NOT NULL DEFAULT '[]',
    violation_codes      TEXT NOT NULL DEFAULT '[]',
    lesson               TEXT NOT NULL DEFAULT '',
    user_note            TEXT NOT NULL DEFAULT '',
    market_context_tags  TEXT NOT NULL DEFAULT '[]',
    behavior_tag         TEXT NOT NULL DEFAULT '',
    emotion_tag          TEXT NOT NULL DEFAULT '',
    symbol               TEXT NOT NULL DEFAULT '',
    holding_period       TEXT NOT NULL DEFAULT '',
    earning_type         TEXT NOT NULL DEFAULT '',
    pattern_key          TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    source               TEXT NOT NULL DEFAULT 'review_confirmed',
    CHECK (primary_error != 'NONE')
);
CREATE INDEX IF NOT EXISTS idx_mistake_key ON mistake_instance(pattern_key);
CREATE INDEX IF NOT EXISTS idx_mistake_error ON mistake_instance(primary_error);

CREATE TABLE IF NOT EXISTS decision_pattern_fact (
    id             TEXT PRIMARY KEY,
    decision_id    TEXT NOT NULL UNIQUE,
    quadrant       TEXT NOT NULL DEFAULT '',
    primary_error  TEXT NOT NULL DEFAULT 'NONE',
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pattern (
    id                      TEXT PRIMARY KEY,
    pattern_key             TEXT NOT NULL UNIQUE,
    status                  TEXT NOT NULL DEFAULT 'OBSERVED',
    summary                 TEXT NOT NULL DEFAULT '',
    common_trigger          TEXT NOT NULL DEFAULT '',
    common_behavior         TEXT NOT NULL DEFAULT '',
    occurrence_count        INTEGER NOT NULL DEFAULT 0,
    last_seen_at            TEXT NOT NULL DEFAULT '',
    dismissed_evidence_hash TEXT NOT NULL DEFAULT '',
    created_at              TEXT NOT NULL,
    confirmed_at            TEXT NOT NULL DEFAULT '',
    dismissed_at            TEXT NOT NULL DEFAULT '',
    confirmed_by            TEXT NOT NULL DEFAULT '',
    merged_into             TEXT NOT NULL DEFAULT '',
    CHECK (status IN ('OBSERVED','CANDIDATE','CONFIRMED','DISMISSED'))
);
CREATE INDEX IF NOT EXISTS idx_pattern_status ON pattern(status);

CREATE TABLE IF NOT EXISTS pattern_evidence (
    pattern_id   TEXT NOT NULL,
    mistake_id   TEXT NOT NULL,
    decision_id  TEXT NOT NULL,
    added_at     TEXT NOT NULL,
    PRIMARY KEY (pattern_id, mistake_id)
);
CREATE INDEX IF NOT EXISTS idx_pattern_ev_decision ON pattern_evidence(decision_id);

CREATE TABLE IF NOT EXISTS rule (
    id                     TEXT PRIMARY KEY,
    pattern_id             TEXT NOT NULL,
    rule_text              TEXT NOT NULL,
    trigger_text           TEXT NOT NULL DEFAULT '',
    expected_behavior      TEXT NOT NULL DEFAULT '',
    scope_json             TEXT NOT NULL DEFAULT '{}',
    evidence_count         INTEGER NOT NULL DEFAULT 0,
    evidence_decision_ids  TEXT NOT NULL DEFAULT '[]',
    proposed_by            TEXT NOT NULL DEFAULT 'system',
    status                 TEXT NOT NULL DEFAULT 'DRAFT',
    created_at             TEXT NOT NULL,
    confirmed_at           TEXT NOT NULL DEFAULT '',
    retired_at             TEXT NOT NULL DEFAULT '',
    retire_reason          TEXT NOT NULL DEFAULT '',
    CHECK (status IN ('DRAFT','PROPOSED','ACTIVE','REJECTED','RETIRED'))
);
CREATE INDEX IF NOT EXISTS idx_rule_pattern ON rule(pattern_id);
CREATE INDEX IF NOT EXISTS idx_rule_status ON rule(status);

CREATE TABLE IF NOT EXISTS rule_revision (
    id          TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    old_text    TEXT NOT NULL DEFAULT '',
    new_text    TEXT NOT NULL DEFAULT '',
    old_status  TEXT NOT NULL DEFAULT '',
    new_status  TEXT NOT NULL DEFAULT '',
    reason      TEXT NOT NULL,
    changed_at  TEXT NOT NULL,
    changed_by  TEXT NOT NULL DEFAULT 'user'
);
CREATE INDEX IF NOT EXISTS idx_rule_rev_rule ON rule_revision(rule_id);

CREATE TABLE IF NOT EXISTS rule_violation (
    id              TEXT PRIMARY KEY,
    rule_id         TEXT NOT NULL,
    decision_id     TEXT NOT NULL,
    detected_at     TEXT NOT NULL,
    evidence        TEXT NOT NULL DEFAULT '{}',
    user_confirmed  INTEGER NOT NULL DEFAULT 0,
    confirmed_at    TEXT NOT NULL DEFAULT '',
    UNIQUE (rule_id, decision_id)
);
CREATE INDEX IF NOT EXISTS idx_rule_vio_rule ON rule_violation(rule_id);

CREATE TABLE IF NOT EXISTS memory_reminder (
    id                     TEXT PRIMARY KEY,
    decision_id            TEXT NOT NULL,
    rule_id                TEXT NOT NULL,
    why                    TEXT NOT NULL DEFAULT '',
    evidence_decision_ids  TEXT NOT NULL DEFAULT '[]',
    created_at             TEXT NOT NULL,
    feedback               TEXT NOT NULL DEFAULT '',
    feedback_at            TEXT NOT NULL DEFAULT '',
    CHECK (feedback IN ('','RELEVANT','NOT_RELEVANT'))
);
CREATE INDEX IF NOT EXISTS idx_reminder_decision ON memory_reminder(decision_id);
