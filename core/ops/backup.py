"""SQLite backup / restore 校验。不回写生产库。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List

CRITICAL = (
    "decision",
    "execution",
    "review",
    "attribution",
    "mistake_instance",
    "pattern",
    "rule",
    "revision",
    "decision_transition",
)


def _tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return int(conn.execute("SELECT COUNT(*) FROM {0}".format(table)).fetchone()[0])
    except sqlite3.Error:
        return -1


def checksum(conn: sqlite3.Connection, table: str) -> str:
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info({0})".format(table))]
        if "id" in cols:
            order = "id"
        else:
            order = cols[0] if cols else "rowid"
        rows = conn.execute("SELECT * FROM {0} ORDER BY {1}".format(table, order)).fetchall()
    except sqlite3.Error:
        return ""
    blob = json.dumps([tuple(r) for r in rows], ensure_ascii=False, default=str, sort_keys=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def snapshot(path: Path) -> Dict[str, Any]:
    conn = sqlite3.connect(str(path))
    try:
        tables = _tables(conn)
        counts = {t: _count(conn, t) for t in CRITICAL if t in tables}
        hashes = {t: checksum(conn, t) for t in CRITICAL if t in tables}
        return {"tables": tables, "counts": counts, "hashes": hashes}
    finally:
        conn.close()


def backup_to(src: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(src))
    target = sqlite3.connect(str(dest))
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    return dest


def verify(src: Path, include_empty: bool = True) -> Dict[str, Any]:
    if not src.exists():
        return {"ok": False, "status": "FAIL", "reason": "source db missing: {0}".format(src)}
    tmp = Path(tempfile.mkdtemp(prefix="sa-bak-"))
    bak = backup_to(src, tmp / "backup.db")
    restored = backup_to(bak, tmp / "restored.db")
    before = snapshot(src)
    after = snapshot(restored)
    mismatches = []
    for table in CRITICAL:
        if before["counts"].get(table, -1) != after["counts"].get(table, -1):
            mismatches.append("count:{0}".format(table))
        if before["hashes"].get(table) != after["hashes"].get(table):
            mismatches.append("hash:{0}".format(table))
    ok = not mismatches
    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "source": str(src),
        "backup": str(bak),
        "restored": str(restored),
        "before": before["counts"],
        "after": after["counts"],
        "mismatches": mismatches,
        "include_empty": include_empty,
    }
