-- 0002_execution_intake
-- P1.1 收盘导入：给 execution 加去重指纹与匹配审计，给 decision 加 account。
-- 不删表、不删数据。529 笔 legacy execution 只补 fingerprint 回填，原字段一律不动。

-- ------------------------------------------------------------ execution 扩列
ALTER TABLE execution ADD COLUMN account         TEXT NOT NULL DEFAULT '';
ALTER TABLE execution ADD COLUMN broker_order_id TEXT NOT NULL DEFAULT '';
-- 稳定去重键。优先 broker_order_id，否则由 account/code/时间/方向/价/量 派生。
ALTER TABLE execution ADD COLUMN fingerprint     TEXT NOT NULL DEFAULT '';
-- 匹配审计：谁把这笔挂到 Decision 上的，依据是什么。
ALTER TABLE execution ADD COLUMN match_status    TEXT NOT NULL DEFAULT '';
ALTER TABLE execution ADD COLUMN matched_at      TEXT NOT NULL DEFAULT '';
ALTER TABLE execution ADD COLUMN matched_by      TEXT NOT NULL DEFAULT '';
ALTER TABLE execution ADD COLUMN match_reason    TEXT NOT NULL DEFAULT '';
ALTER TABLE execution ADD COLUMN matcher_version TEXT NOT NULL DEFAULT '';

-- legacy 行的 trade_id 本身就是稳定去重键，直接当 fingerprint 用。
-- 这是补空字段，不改任何已有值。
UPDATE execution SET fingerprint = trade_id WHERE fingerprint = '' AND trade_id != '';

-- 空 fingerprint 不参与唯一约束（历史上可能有手工录入的行没有指纹）。
CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_fingerprint
    ON execution(fingerprint) WHERE fingerprint != '';
CREATE INDEX IF NOT EXISTS idx_execution_match_status ON execution(match_status);
CREATE INDEX IF NOT EXISTS idx_execution_account ON execution(account, code);

-- ------------------------------------------------------------- decision 扩列
-- 同一标的在不同账户是两条独立决策线，匹配时必须区分。
ALTER TABLE decision ADD COLUMN account TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_decision_account ON decision(account, code);

-- -------------------------------------------------------- match_candidate
-- 匹配候选。每次匹配整体重算，只对尚未确定归属的 execution 保留。
-- score 只是给人排序用的启发式分值，不是概率，不参与任何自动绑定判断。
CREATE TABLE IF NOT EXISTS match_candidate (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id    TEXT NOT NULL REFERENCES execution(id),
    decision_id     TEXT NOT NULL REFERENCES decision(id),
    rank            INTEGER NOT NULL,
    score           REAL NOT NULL,
    reason          TEXT NOT NULL DEFAULT '',
    computed_at     TEXT NOT NULL,
    matcher_version TEXT NOT NULL DEFAULT 'm1'
);
CREATE INDEX IF NOT EXISTS idx_candidate_execution ON match_candidate(execution_id, rank);

-- --------------------------------------------------------- intake_run
-- 每次收盘导入留一条运行记录，便于回答「今天这批是什么时候、从哪导进来的」。
CREATE TABLE IF NOT EXISTS intake_run (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date   TEXT NOT NULL,
    ran_at       TEXT NOT NULL,
    adapter      TEXT NOT NULL DEFAULT '',
    source_ref   TEXT NOT NULL DEFAULT '',
    rows_in      INTEGER NOT NULL DEFAULT 0,
    inserted     INTEGER NOT NULL DEFAULT 0,
    duplicate    INTEGER NOT NULL DEFAULT 0,
    non_trade    INTEGER NOT NULL DEFAULT 0,
    unparseable  INTEGER NOT NULL DEFAULT 0,
    auto_matched INTEGER NOT NULL DEFAULT 0,
    review_required INTEGER NOT NULL DEFAULT 0,
    no_candidate INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_intake_run_date ON intake_run(trade_date, id);
