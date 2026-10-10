-- 0001_review_core
-- Review Agent P0：把 Decision 从一张 26 列宽表拆成关系模型。
-- 旧 26 列宽表已改名 decision_legacy（0 行），CSV 保留为兼容导出层。
-- 约束来源见 config/review.yaml（P0.0 冻结定义）。

-- ---------------------------------------------------------------- decision
-- 决策头：一笔决策里不会变的部分。可变部分在 plan / expectation，历史在 revision。
CREATE TABLE IF NOT EXISTS decision (
    id                 TEXT PRIMARY KEY,
    opened_on          TEXT NOT NULL,                      -- 决策日（事前）
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
    -- 主观字段是否可得。legacy 重建的决策一律 unavailable，不得被推断补全。
    subjective_context TEXT NOT NULL DEFAULT 'available',
    legacy_reconstructed INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    effective_at       TEXT NOT NULL,
    source             TEXT NOT NULL DEFAULT 'user',
    created_by         TEXT NOT NULL DEFAULT 'user',
    revision           INTEGER NOT NULL DEFAULT 1,
    CHECK (status IN ('DRAFT','PLANNED','ACTIVE','CLOSED','REVIEW_PENDING',
                      'REVIEWED','CANCELLED','EXPIRED')),
    CHECK (subjective_context IN ('available','unavailable'))
);
CREATE INDEX IF NOT EXISTS idx_decision_status ON decision(status);
CREATE INDEX IF NOT EXISTS idx_decision_code ON decision(code);
CREATE INDEX IF NOT EXISTS idx_decision_opened ON decision(opened_on);

-- ------------------------------------------------------------- expectation
-- Decision 1:N Expectation。P0 不编译 predicate，但字段先占位并冻结语义。
CREATE TABLE IF NOT EXISTS expectation (
    id                TEXT PRIMARY KEY,
    decision_id       TEXT NOT NULL REFERENCES decision(id),
    raw_text          TEXT NOT NULL,                       -- 用户原话，永不改写
    predicate_json    TEXT NOT NULL DEFAULT '',
    predicate_version INTEGER NOT NULL DEFAULT 0,
    compiler          TEXT NOT NULL DEFAULT '',
    compiler_version  TEXT NOT NULL DEFAULT '',
    user_confirmed    INTEGER NOT NULL DEFAULT 0,
    confirmed_at      TEXT NOT NULL DEFAULT '',
    window_start      TEXT NOT NULL DEFAULT '',            -- evaluation_window 起
    window_end        TEXT NOT NULL DEFAULT '',            -- evaluation_window 止
    confidence        INTEGER,                             -- 用户自评 1–5
    status            TEXT NOT NULL DEFAULT 'OPEN',
    verdict           TEXT NOT NULL DEFAULT 'PENDING',
    evaluated_at      TEXT NOT NULL DEFAULT '',
    evaluation_note   TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    effective_at      TEXT NOT NULL,
    source            TEXT NOT NULL DEFAULT 'user',
    created_by        TEXT NOT NULL DEFAULT 'user',
    revision          INTEGER NOT NULL DEFAULT 1,
    CHECK (status IN ('OPEN','FROZEN','EVALUATED','VOID')),
    CHECK (verdict IN ('PENDING','CORRECT','PARTIAL','WRONG','UNVERIFIABLE'))
);
CREATE INDEX IF NOT EXISTS idx_expectation_decision ON expectation(decision_id);
CREATE INDEX IF NOT EXISTS idx_expectation_verdict ON expectation(verdict);

-- -------------------------------------------------------------------- plan
-- Decision 1:N Plan。改计划 = 追加新 revision，旧版本置 superseded_by，不覆盖。
CREATE TABLE IF NOT EXISTS plan (
    id                  TEXT PRIMARY KEY,
    decision_id         TEXT NOT NULL REFERENCES decision(id),
    revision            INTEGER NOT NULL DEFAULT 1,
    entry_rule          TEXT NOT NULL DEFAULT '',
    entry_window_start  TEXT NOT NULL DEFAULT '',
    entry_window_end    TEXT NOT NULL DEFAULT '',
    target_size_pct     REAL,                              -- 计划仓位占净值 %
    target_size_amount  REAL,                              -- 或计划金额
    add_rule            TEXT NOT NULL DEFAULT '',
    reduce_rule         TEXT NOT NULL DEFAULT '',
    stop_price          REAL,
    stop_rule           TEXT NOT NULL DEFAULT '',
    invalidation        TEXT NOT NULL DEFAULT '',
    holding_period      TEXT NOT NULL DEFAULT '',
    superseded_by       TEXT NOT NULL DEFAULT '',
    reason_for_revision TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    effective_at        TEXT NOT NULL,
    source              TEXT NOT NULL DEFAULT 'user',
    created_by          TEXT NOT NULL DEFAULT 'user'
);
CREATE INDEX IF NOT EXISTS idx_plan_decision ON plan(decision_id, revision);

-- --------------------------------------------------------------- execution
-- Decision 1:N Execution。decision_id 可为 NULL —— 历史流水先只落这里。
CREATE TABLE IF NOT EXISTS execution (
    id                 TEXT PRIMARY KEY,
    decision_id        TEXT REFERENCES decision(id),
    trade_id           TEXT NOT NULL DEFAULT '',
    executed_on        TEXT NOT NULL,
    executed_at        TEXT NOT NULL DEFAULT '',
    code               TEXT NOT NULL,
    name               TEXT NOT NULL DEFAULT '',
    side               TEXT NOT NULL,                      -- BUY / SELL
    action             TEXT NOT NULL DEFAULT '',           -- OPEN/ADD/REDUCE/CLOSE
    price              REAL NOT NULL,
    qty                REAL NOT NULL,
    amount             REAL,
    size_pct           REAL,                               -- 占净值 %，可空
    planned            TEXT NOT NULL DEFAULT 'unknown',    -- yes / no / unknown
    subjective_context TEXT NOT NULL DEFAULT 'available',
    note               TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL,
    effective_at       TEXT NOT NULL,
    source             TEXT NOT NULL DEFAULT 'user',
    created_by         TEXT NOT NULL DEFAULT 'user',
    revision           INTEGER NOT NULL DEFAULT 1,
    CHECK (side IN ('BUY','SELL')),
    CHECK (planned IN ('yes','no','unknown')),
    CHECK (subjective_context IN ('available','unavailable'))
);
CREATE INDEX IF NOT EXISTS idx_execution_decision ON execution(decision_id);
CREATE INDEX IF NOT EXISTS idx_execution_code_date ON execution(code, executed_on);
CREATE INDEX IF NOT EXISTS idx_execution_trade ON execution(trade_id);

-- ----------------------------------------------------------------- outcome
-- Decision 1:1 Outcome。全部由 execution + quote_daily 算出，不接受手填。
CREATE TABLE IF NOT EXISTS outcome (
    decision_id    TEXT PRIMARY KEY REFERENCES decision(id),
    first_entry_on TEXT NOT NULL DEFAULT '',
    closed_on      TEXT NOT NULL DEFAULT '',
    holding_days   INTEGER,
    qty_bought     REAL,
    qty_sold       REAL,
    avg_entry      REAL,
    avg_exit       REAL,
    gross_pnl      REAL,
    realized_pct   REAL,
    mfe_pct        REAL,                                   -- 最大有利偏移
    mae_pct        REAL,                                   -- 最大不利偏移
    peak_on        TEXT NOT NULL DEFAULT '',
    trough_on      TEXT NOT NULL DEFAULT '',
    quote_coverage TEXT NOT NULL DEFAULT 'none',           -- full/partial/none
    computed_at    TEXT NOT NULL,
    computed_from  TEXT NOT NULL DEFAULT 'execution+quote_daily',
    source         TEXT NOT NULL DEFAULT 'system',
    CHECK (quote_coverage IN ('full','partial','none'))
);

-- ------------------------------------------------------------------ review
-- Decision 1:N Review。append-only，一次复盘一行。
CREATE TABLE IF NOT EXISTS review (
    id                   TEXT PRIMARY KEY,
    decision_id          TEXT NOT NULL REFERENCES decision(id),
    kind                 TEXT NOT NULL DEFAULT 'decision',
    reviewed_on          TEXT NOT NULL,
    outcome_confirmed    INTEGER NOT NULL DEFAULT 0,
    violations_confirmed INTEGER NOT NULL DEFAULT 0,
    lesson               TEXT NOT NULL DEFAULT '',
    user_note            TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    effective_at         TEXT NOT NULL,
    source               TEXT NOT NULL DEFAULT 'user',
    created_by           TEXT NOT NULL DEFAULT 'user',
    revision             INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_review_decision ON review(decision_id);

-- ------------------------------------------------------------- attribution
-- Review 1:N Attribution。Layer B：原因判断。不打百分比。
CREATE TABLE IF NOT EXISTS attribution (
    id             TEXT PRIMARY KEY,
    review_id      TEXT NOT NULL REFERENCES review(id),
    decision_id    TEXT NOT NULL REFERENCES decision(id),
    primary_error  TEXT NOT NULL,
    contributing   TEXT NOT NULL DEFAULT '[]',             -- JSON 数组，无权重
    counterfactual TEXT NOT NULL DEFAULT '',               -- 必须可用真实行情验算
    confidence     TEXT NOT NULL DEFAULT 'medium',
    evidence       TEXT NOT NULL DEFAULT '[]',
    user_confirmed INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    effective_at   TEXT NOT NULL,
    source         TEXT NOT NULL DEFAULT 'user',
    created_by     TEXT NOT NULL DEFAULT 'user',
    revision       INTEGER NOT NULL DEFAULT 1,
    CHECK (confidence IN ('high','medium','low'))
);
CREATE INDEX IF NOT EXISTS idx_attribution_decision ON attribution(decision_id);
CREATE INDEX IF NOT EXISTS idx_attribution_review ON attribution(review_id);

-- ------------------------------------------------------- process_violation
-- Layer A：确定性事实，可随时由闸门重算。与 attribution 严格分离。
-- 重算时整条删除重建，但保留用户的 acknowledged 状态。
CREATE TABLE IF NOT EXISTS process_violation (
    id           TEXT PRIMARY KEY,
    decision_id  TEXT NOT NULL REFERENCES decision(id),
    execution_id TEXT NOT NULL DEFAULT '',
    code         TEXT NOT NULL,
    severity     TEXT NOT NULL DEFAULT 'warn',
    detail       TEXT NOT NULL DEFAULT '',
    evidence     TEXT NOT NULL DEFAULT '[]',
    acknowledged INTEGER NOT NULL DEFAULT 0,
    detected_at  TEXT NOT NULL,
    gate_version TEXT NOT NULL DEFAULT 'g1',
    source       TEXT NOT NULL DEFAULT 'system'
);
CREATE INDEX IF NOT EXISTS idx_violation_decision ON process_violation(decision_id);
CREATE INDEX IF NOT EXISTS idx_violation_code ON process_violation(code);

-- ---------------------------------------------------------------- revision
-- 字段级修订历史。改字段 = 追加一行 + 更新投影，原值永不丢失。
CREATE TABLE IF NOT EXISTS revision (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    row_id     TEXT NOT NULL,
    field      TEXT NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    reason     TEXT NOT NULL DEFAULT '',
    changed_at TEXT NOT NULL,
    changed_by TEXT NOT NULL DEFAULT 'user',
    source     TEXT NOT NULL DEFAULT 'user'
);
CREATE INDEX IF NOT EXISTS idx_revision_row ON revision(table_name, row_id);

-- ------------------------------------------------------- decision_transition
-- 状态机事件流水。raw event 不删除，当前 status 是它的投影。
CREATE TABLE IF NOT EXISTS decision_transition (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id   TEXT NOT NULL REFERENCES decision(id),
    from_status   TEXT NOT NULL,
    to_status     TEXT NOT NULL,
    occurred_at   TEXT NOT NULL,
    changed_by    TEXT NOT NULL DEFAULT 'user',
    source        TEXT NOT NULL DEFAULT 'user',
    reason        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_transition_decision
    ON decision_transition(decision_id, id);
