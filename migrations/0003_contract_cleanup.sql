-- 0003_contract_cleanup
-- P1.15：Decision.origin（EX_ANTE / POST_HOC）+ subjective_context 三态。
-- SQLite 不能 ALTER CHECK，所以重建 decision / execution，数据原样搬迁。
-- 不删历史 CSV，不重建 legacy Decision。

PRAGMA foreign_keys = OFF;

-- ---------------------------------------------------------------- decision
CREATE TABLE decision_p115 (
    id                 TEXT PRIMARY KEY,
    opened_on          TEXT NOT NULL,
    code               TEXT NOT NULL DEFAULT '',
    name               TEXT NOT NULL DEFAULT '',
    direction          TEXT NOT NULL DEFAULT 'long',
    thesis             TEXT NOT NULL DEFAULT '',
    earning_type       TEXT NOT NULL DEFAULT '',
    holding_period     TEXT NOT NULL DEFAULT '',
    market_context     TEXT NOT NULL DEFAULT '',
    status             TEXT NOT NULL DEFAULT 'DRAFT',
    closed_on          TEXT NOT NULL DEFAULT '',
    reviewed_at        TEXT NOT NULL DEFAULT '',
    subjective_context TEXT NOT NULL DEFAULT 'not_recorded',
    legacy_reconstructed INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    effective_at       TEXT NOT NULL,
    source             TEXT NOT NULL DEFAULT 'user',
    created_by         TEXT NOT NULL DEFAULT 'user',
    revision           INTEGER NOT NULL DEFAULT 1,
    account            TEXT NOT NULL DEFAULT '',
    origin             TEXT NOT NULL DEFAULT 'EX_ANTE',
    CHECK (status IN ('DRAFT','PLANNED','ACTIVE','CLOSED','REVIEW_PENDING',
                      'REVIEWED','CANCELLED','EXPIRED')),
    CHECK (subjective_context IN ('available','not_recorded','unavailable')),
    CHECK (origin IN ('EX_ANTE','POST_HOC'))
);

INSERT INTO decision_p115 (
    id, opened_on, code, name, direction, thesis, earning_type, holding_period,
    market_context, status, closed_on, reviewed_at, subjective_context,
    legacy_reconstructed, created_at, effective_at, source, created_by, revision,
    account, origin
)
SELECT
    id, opened_on, code, name, direction, thesis, earning_type, holding_period,
    market_context, status, closed_on, reviewed_at, subjective_context,
    legacy_reconstructed, created_at, effective_at, source, created_by, revision,
    account,
    CASE WHEN COALESCE(legacy_reconstructed, 0) = 1 THEN 'POST_HOC' ELSE 'EX_ANTE' END
FROM decision;

DROP TABLE decision;
ALTER TABLE decision_p115 RENAME TO decision;

CREATE INDEX IF NOT EXISTS idx_decision_status ON decision(status);
CREATE INDEX IF NOT EXISTS idx_decision_code ON decision(code);
CREATE INDEX IF NOT EXISTS idx_decision_opened ON decision(opened_on);
CREATE INDEX IF NOT EXISTS idx_decision_account ON decision(account, code);
CREATE INDEX IF NOT EXISTS idx_decision_origin ON decision(origin);

-- --------------------------------------------------------------- execution
CREATE TABLE execution_p115 (
    id                 TEXT PRIMARY KEY,
    decision_id        TEXT REFERENCES decision(id),
    trade_id           TEXT NOT NULL DEFAULT '',
    executed_on        TEXT NOT NULL,
    executed_at        TEXT NOT NULL DEFAULT '',
    code               TEXT NOT NULL,
    name               TEXT NOT NULL DEFAULT '',
    side               TEXT NOT NULL,
    action             TEXT NOT NULL DEFAULT '',
    price              REAL NOT NULL,
    qty                REAL NOT NULL,
    amount             REAL,
    size_pct           REAL,
    planned            TEXT NOT NULL DEFAULT 'unknown',
    subjective_context TEXT NOT NULL DEFAULT 'not_recorded',
    note               TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    effective_at       TEXT NOT NULL,
    source             TEXT NOT NULL DEFAULT 'user',
    created_by         TEXT NOT NULL DEFAULT 'user',
    revision           INTEGER NOT NULL DEFAULT 1,
    account            TEXT NOT NULL DEFAULT '',
    broker_order_id    TEXT NOT NULL DEFAULT '',
    fingerprint        TEXT NOT NULL DEFAULT '',
    match_status       TEXT NOT NULL DEFAULT '',
    matched_at         TEXT NOT NULL DEFAULT '',
    matched_by         TEXT NOT NULL DEFAULT '',
    match_reason       TEXT NOT NULL DEFAULT '',
    matcher_version    TEXT NOT NULL DEFAULT '',
    CHECK (side IN ('BUY','SELL')),
    CHECK (planned IN ('yes','no','unknown')),
    CHECK (subjective_context IN ('available','not_recorded','unavailable'))
);

INSERT INTO execution_p115 (
    id, decision_id, trade_id, executed_on, executed_at, code, name, side, action,
    price, qty, amount, size_pct, planned, subjective_context, note,
    created_at, effective_at, source, created_by, revision, account,
    broker_order_id, fingerprint, match_status, matched_at, matched_by,
    match_reason, matcher_version
)
SELECT
    id, decision_id, trade_id, executed_on, executed_at, code, name, side, action,
    price, qty, amount, size_pct, planned, subjective_context, note,
    created_at, effective_at, source, created_by, revision, account,
    broker_order_id, fingerprint, match_status, matched_at, matched_by,
    match_reason, matcher_version
FROM execution;

DROP TABLE execution;
ALTER TABLE execution_p115 RENAME TO execution;

CREATE INDEX IF NOT EXISTS idx_execution_decision ON execution(decision_id);
CREATE INDEX IF NOT EXISTS idx_execution_code_date ON execution(code, executed_on);
CREATE INDEX IF NOT EXISTS idx_execution_trade ON execution(trade_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_fingerprint
    ON execution(fingerprint) WHERE fingerprint != '';
CREATE INDEX IF NOT EXISTS idx_execution_match_status ON execution(match_status);
CREATE INDEX IF NOT EXISTS idx_execution_account ON execution(account, code);

PRAGMA foreign_keys = ON;
