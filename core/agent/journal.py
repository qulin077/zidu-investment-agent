"""轻量对话日记。

日记保存用户原话和可重做摘要，不是 Research / Decision / Review 的事实源。
正式决策仍走 Recorder Write Gate。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from core.agent.store import dumps, loads
from core.config import SETTINGS, TRADING_DIR
from core.research.store import _ids, now_iso
from core.store import Store

ENTRY_TYPES = {"FEELING", "THOUGHT", "TRADE_NOTE", "REVIEW_NOTE", "GENERAL"}


def save(
    store: Store,
    *,
    session_id: str,
    source_message_id: str,
    raw_text: str,
    summary: str = "",
    entry_type: str = "GENERAL",
    entity_refs: list | None = None,
    created_at: str = "",
) -> dict:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("日记原文为空")
    kind = (entry_type or "GENERAL").upper()
    if kind not in ENTRY_TYPES:
        kind = "GENERAL"
    stamp = created_at or now_iso()
    day = stamp[:10]
    entities = [row for row in (entity_refs or []) if isinstance(row, dict)]
    with store.connect() as conn:
        entry_id = _ids(conn, "agent_journal_entry", "AJ", 1)[0]
        conn.execute(
            """INSERT INTO agent_journal_entry
               (id, session_id, source_message_id, entry_date, entry_type,
                raw_text, summary, entity_refs_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (entry_id, session_id, source_message_id, day, kind, text,
             (summary or "").strip(), dumps(entities), stamp),
        )
    row = get(store, entry_id)
    _append_markdown(store, row)
    return row


def get(store: Store, entry_id: str) -> dict:
    rows = store.query("SELECT * FROM agent_journal_entry WHERE id = ?", (entry_id,))
    if not rows:
        return {}
    row = dict(rows[0])
    row["entity_refs"] = loads(row.get("entity_refs_json"), [])
    return row


def list_entries(store: Store, *, day: str = "", session_id: str = "", limit: int = 20) -> list:
    where = []
    args = []
    if day:
        where.append("entry_date = ?")
        args.append(day)
    if session_id:
        where.append("session_id = ?")
        args.append(session_id)
    sql = "SELECT * FROM agent_journal_entry"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 100)))
    rows = store.query(sql, tuple(args))
    out = []
    for item in rows:
        row = dict(item)
        row["entity_refs"] = loads(row.get("entity_refs_json"), [])
        out.append(row)
    return out


def _append_markdown(store: Store, row: dict) -> None:
    target = _journal_dir(store)
    if target is None:
        return
    target.mkdir(parents=True, exist_ok=True)
    path = target / "{0}.md".format(row["entry_date"])
    if not path.exists():
        path.write_text(
            "# 对话日记 · {0}\n\n> 用户原话与轻量摘要。不是正式 Research、Decision 或 Rule。\n".format(row["entry_date"]),
            encoding="utf-8",
        )
    stamp = row.get("created_at") or ""
    try:
        clock = datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        clock = stamp[11:16] or "--:--"
    summary = (row.get("summary") or "").strip()
    block = "\n## {0} · {1}\n\n> {2}\n".format(clock, row.get("entry_type") or "GENERAL", row.get("raw_text") or "")
    if summary and summary != row.get("raw_text"):
        block += "\n摘要：{0}\n".format(summary)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(block)


def _journal_dir(store: Store) -> Path | None:
    override = (os.environ.get("SA_JOURNAL_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    try:
        if Path(store.path).resolve() != Path(SETTINGS.db_path).resolve():
            return None
    except OSError:
        return None
    return TRADING_DIR / "对话日记"
