"""SQLite 存储层。

把 625 个散落的 csv/json 收敛成若干张表。选 SQLite 而非 Postgres 的理由是
单用户、百级标的、日频数据，零运维且能直接进现有备份流程；所有访问都经过
本模块，将来换 Postgres 只需替换实现，调用方不动。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from core.config import SETTINGS, Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS instrument (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    sector      TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL DEFAULT '',
    board       TEXT NOT NULL DEFAULT '',
    priority    INTEGER NOT NULL DEFAULT 99
);

CREATE TABLE IF NOT EXISTS quote_daily (
    code        TEXT NOT NULL,
    date        TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      REAL,
    pct_chg     REAL,
    PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_quote_date ON quote_daily(date);

CREATE TABLE IF NOT EXISTS news_item (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    published_at TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL DEFAULT '',
    summary      TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_item(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_source ON news_item(source);

CREATE TABLE IF NOT EXISTS position_snapshot (
    date        TEXT NOT NULL,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    qty         REAL,
    cost        REAL,
    price       REAL,
    mkt_value   REAL,
    pnl_pct     REAL,
    sector      TEXT NOT NULL DEFAULT '',
    weight_pct  REAL,
    note        TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (date, code)
);

CREATE TABLE IF NOT EXISTS account_snapshot (
    date          TEXT PRIMARY KEY,
    equity        REAL,
    mkt_value     REAL,
    cash          REAL,
    pnl_total     REAL,
    pnl_day       REAL,
    pnl_day_pct   REAL,
    position_pct  REAL,
    source        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS trade (
    id           TEXT PRIMARY KEY,
    date         TEXT NOT NULL,
    time         TEXT NOT NULL DEFAULT '',
    code         TEXT NOT NULL,
    name         TEXT NOT NULL DEFAULT '',
    side         TEXT NOT NULL DEFAULT '',
    price        REAL,
    qty          REAL,
    amount       REAL,
    strategy     TEXT NOT NULL DEFAULT '',
    earning_type TEXT NOT NULL DEFAULT '',
    reason       TEXT NOT NULL DEFAULT '',
    emotion      TEXT NOT NULL DEFAULT '',
    planned      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_trade_date ON trade(date);
CREATE INDEX IF NOT EXISTS idx_trade_code ON trade(code);

CREATE TABLE IF NOT EXISTS dataset_run (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset   TEXT NOT NULL,
    ran_at    TEXT NOT NULL,
    asof      TEXT NOT NULL DEFAULT '',
    rows      INTEGER NOT NULL DEFAULT 0,
    ok        INTEGER NOT NULL DEFAULT 1,
    message   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_run_dataset ON dataset_run(dataset, ran_at DESC);

CREATE TABLE IF NOT EXISTS decision_legacy (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL DEFAULT '',
    code TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    side TEXT NOT NULL DEFAULT '',
    thesis TEXT NOT NULL DEFAULT '',
    expectation TEXT NOT NULL DEFAULT '',
    plan_entry TEXT NOT NULL DEFAULT '',
    plan_stop TEXT NOT NULL DEFAULT '',
    plan_size TEXT NOT NULL DEFAULT '',
    planned TEXT NOT NULL DEFAULT '',
    earning_type TEXT NOT NULL DEFAULT '',
    invalidation TEXT NOT NULL DEFAULT '',
    holding_period TEXT NOT NULL DEFAULT '',
    market_context TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    trade_ids TEXT NOT NULL DEFAULT '',
    prediction_ids TEXT NOT NULL DEFAULT '',
    actual_summary TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    error_type TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    emotion TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    reviewed_at TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT ''
);
"""


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: Sequence[str]
    conflict: Sequence[str]


TABLES: Dict[str, TableSpec] = {
    "instrument": TableSpec(
        "instrument", ("code", "name", "sector", "role", "board", "priority"), ("code",)
    ),
    "quote_daily": TableSpec(
        "quote_daily",
        ("code", "date", "open", "high", "low", "close", "volume", "pct_chg"),
        ("code", "date"),
    ),
    "news_item": TableSpec(
        "news_item",
        ("id", "source", "published_at", "title", "url", "summary", "tags"),
        ("id",),
    ),
    "position_snapshot": TableSpec(
        "position_snapshot",
        (
            "date", "code", "name", "qty", "cost", "price",
            "mkt_value", "pnl_pct", "sector", "weight_pct", "note",
        ),
        ("date", "code"),
    ),
    "account_snapshot": TableSpec(
        "account_snapshot",
        (
            "date", "equity", "mkt_value", "cash", "pnl_total",
            "pnl_day", "pnl_day_pct", "position_pct", "source",
        ),
        ("date",),
    ),
    "trade": TableSpec(
        "trade",
        (
            "id", "date", "time", "code", "name", "side", "price", "qty",
            "amount", "strategy", "earning_type", "reason", "emotion", "planned",
        ),
        ("id",),
    ),
    "decision_legacy": TableSpec(
        "decision_legacy",
        (
            "id", "date", "code", "name", "side", "thesis", "expectation",
            "plan_entry", "plan_stop", "plan_size", "planned", "earning_type",
            "invalidation", "holding_period", "market_context", "evidence",
            "trade_ids", "prediction_ids", "actual_summary", "outcome",
            "error_type", "tags", "emotion", "status", "reviewed_at", "note",
        ),
        ("id",),
    ),
}


class Store:
    def __init__(self, settings: Settings = SETTINGS) -> None:
        self._path = settings.db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self):
        return self._path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self._path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """建基础表，然后把 migrations/ 下未执行的迁移补上。

        迁移在这里触发而不是只在 CLI，是为了 API / MCP / 测试启动时拿到的
        库结构一致 —— 否则 review 表只在跑过 CLI 的机器上存在。
        """
        with self.connect() as conn:
            conn.executescript(SCHEMA)
        from core.review import migrate  # 延迟导入：migrate 依赖 Store

        migrate.apply_all(self)

    # -- 写入 --------------------------------------------------------

    def upsert(self, table: str, rows: Iterable[Dict[str, Any]]) -> int:
        """按主键覆盖写入。返回实际写入行数。"""
        spec = TABLES.get(table)
        if spec is None:
            raise KeyError("未声明的表: {0}".format(table))
        payload = list(rows)
        if not payload:
            return 0

        columns = list(spec.columns)
        placeholders = ", ".join("?" for _ in columns)
        updatable = [c for c in columns if c not in spec.conflict]
        update_clause = ", ".join("{0}=excluded.{0}".format(c) for c in updatable)
        sql = "INSERT INTO {table} ({cols}) VALUES ({ph}) ON CONFLICT({keys}) DO UPDATE SET {upd}".format(
            table=spec.name,
            cols=", ".join(columns),
            ph=placeholders,
            keys=", ".join(spec.conflict),
            upd=update_clause or "{0}={0}".format(spec.conflict[0]),
        )
        values = [tuple(row.get(col) for col in columns) for row in payload]
        with self.connect() as conn:
            conn.executemany(sql, values)
        return len(values)

    def record_run(
        self,
        dataset: str,
        ran_at: str,
        asof: str = "",
        rows: int = 0,
        ok: bool = True,
        message: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO dataset_run (dataset, ran_at, asof, rows, ok, message)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (dataset, ran_at, asof, rows, 1 if ok else 0, message),
            )

    # -- 读取 --------------------------------------------------------

    def query(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(sql, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        rows = self.query(sql, params)
        if not rows:
            return None
        return next(iter(rows[0].values()))

    def count(self, table: str) -> int:
        return int(self.scalar("SELECT COUNT(*) FROM {0}".format(table)) or 0)

    def max_date(self, table: str, column: str = "date") -> Optional[str]:
        value = self.scalar("SELECT MAX({0}) FROM {1}".format(column, table))
        return str(value) if value else None

    def last_run(self, dataset: str) -> Optional[Dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM dataset_run WHERE dataset = ? ORDER BY ran_at DESC LIMIT 1",
            (dataset,),
        )
        return rows[0] if rows else None


STORE = Store()
