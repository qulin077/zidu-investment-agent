"""迁移运行器。

选最小实现：一个 schema_migration 表记已应用的文件名，按文件名排序依次执行。
不做 down migration —— 单用户本地库，回滚靠备份比靠反向 SQL 可靠。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List

from core.config import ROOT
from core.store import STORE, Store

MIGRATIONS_DIR = ROOT / "migrations"

_TRACKER = """
CREATE TABLE IF NOT EXISTS schema_migration (
    name       TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

# 旧 26 列宽表的指纹。命中就说明这是 V0 的 decision 表，需要让位给新模型。
_LEGACY_MARKERS = {"actual_summary", "plan_entry", "prediction_ids"}

_ADD_COLUMN = re.compile(
    r"ALTER TABLE\s+(\w+)\s+ADD COLUMN\s+(\w+)[^;]*;",
    re.IGNORECASE | re.DOTALL,
)


def _columns(conn, table: str) -> set:
    rows = conn.execute("PRAGMA table_info({0})".format(table)).fetchall()
    return {row[1] for row in rows}


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _retire_legacy_decision(conn) -> bool:
    """把 V0 的宽表 decision 改名为 decision_legacy，腾出表名给新模型。

    宽表在改名时是 0 行（引擎从未真正运行过），所以这里不搬数据。
    """
    if not _table_exists(conn, "decision"):
        return False
    if not _LEGACY_MARKERS.issubset(_columns(conn, "decision")):
        return False  # 已经是新 schema
    if _table_exists(conn, "decision_legacy"):
        n_legacy = conn.execute("SELECT COUNT(*) FROM decision_legacy").fetchone()[0]
        n_old = conn.execute("SELECT COUNT(*) FROM decision").fetchone()[0]
        if int(n_legacy or 0) == 0:
            conn.execute("DROP TABLE decision_legacy")
            conn.execute("ALTER TABLE decision RENAME TO decision_legacy")
            return True
        if int(n_old or 0) == 0:
            conn.execute("DROP TABLE decision")
            return True
        conn.execute("DROP TABLE decision")
        return True
    conn.execute("ALTER TABLE decision RENAME TO decision_legacy")
    return True


def pending(store: Store = STORE) -> List[str]:
    files = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
    with store.connect() as conn:
        conn.executescript(_TRACKER)
        done = {r[0] for r in conn.execute("SELECT name FROM schema_migration")}
    return [f for f in files if f not in done]


def _skip_existing_add_columns(conn, sql: str) -> str:
    """SQLite 的 ADD COLUMN 不能重跑。已有列则去掉对应语句。"""

    def repl(match: re.Match) -> str:
        table, col = match.group(1), match.group(2)
        if col in _columns(conn, table):
            return ""
        return match.group(0)

    return _ADD_COLUMN.sub(repl, sql)


def apply_all(store: Store = STORE) -> List[str]:
    """应用所有未执行的迁移。幂等。"""
    todo = pending(store)
    if not todo:
        return []
    applied: List[str] = []
    with store.connect() as conn:
        _retire_legacy_decision(conn)
        for name in todo:
            sql = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
            sql = _skip_existing_add_columns(conn, sql)
            if sql.strip():
                conn.executescript(sql)
            conn.execute(
                "INSERT OR REPLACE INTO schema_migration (name, applied_at) VALUES (?, ?)",
                (name, datetime.now().isoformat(timespec="seconds")),
            )
            applied.append(name)
    return applied


def status(store: Store = STORE) -> dict:
    with store.connect() as conn:
        conn.executescript(_TRACKER)
        done = [
            dict(row)
            for row in conn.execute(
                "SELECT name, applied_at FROM schema_migration ORDER BY name"
            )
        ]
    return {
        "applied": done,
        "pending": pending(store),
        "dir": str(MIGRATIONS_DIR),
        "db": str(store.path),
    }
