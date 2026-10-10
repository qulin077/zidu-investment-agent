"""主对话的存储。事实仍在研究、决策和记忆表里。"""
from __future__ import annotations

import json

from core.research.store import _ids, now_iso
from core.store import Store

_HIDDEN = {"chain_of_thought", "thinking", "reasoning", "hidden", "cot"}


def loads(raw, fallback):
    try:
        value = json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def main_session(store: Store) -> dict:
    rows = store.query(
        "SELECT * FROM agent_session WHERE status = 'OPEN' ORDER BY created_at LIMIT 1"
    )
    if rows:
        return _session(rows[0])
    stamp = now_iso()
    with store.connect() as conn:
        session_id = _ids(conn, "agent_session", "AS", 1)[0]
        conn.execute(
            """INSERT INTO agent_session
               (id, title, status, active_goal_id, active_project_id, active_decision_id,
                current_domain, summary_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (session_id, "Investment Agent", "OPEN", "", "", "", "GENERAL", "{}", stamp, stamp),
        )
    return get_session(store, session_id)


def get_session(store: Store, session_id: str) -> dict:
    rows = store.query("SELECT * FROM agent_session WHERE id = ?", (session_id,))
    if not rows:
        return {}
    return _session(rows[0])


def _session(row: dict) -> dict:
    item = dict(row)
    item["summary"] = loads(item.get("summary_json"), {})
    return item


def save_session(store: Store, session_id: str, **fields) -> None:
    allowed = {
        "title", "status", "active_goal_id", "active_project_id", "active_decision_id",
        "active_strategy_id", "current_domain", "summary_json",
    }
    if "summary" in fields and "summary_json" not in fields:
        fields["summary_json"] = dumps(fields.pop("summary"))
    fields["updated_at"] = now_iso()
    keys = [key for key in fields if key in allowed or key == "updated_at"]
    sql = "UPDATE agent_session SET {0} WHERE id = ?".format(
        ", ".join("{0} = ?".format(key) for key in keys)
    )
    with store.connect() as conn:
        conn.execute(sql, tuple(fields[key] for key in keys) + (session_id,))


def add_message(store: Store, session_id: str, role: str, content: str, **refs) -> str:
    stamp = now_iso()
    with store.connect() as conn:
        message_id = _ids(conn, "agent_message", "AM", 1)[0]
        conn.execute(
            """INSERT INTO agent_message
               (id, session_id, role, content, domain, skill, entity_refs_json,
                project_refs_json, decision_refs_json, claim_refs_json, source_refs_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                message_id, session_id, role, content,
                refs.get("domain") or "GENERAL", refs.get("skill") or "",
                dumps(refs.get("entity_refs") or []),
                dumps(refs.get("project_refs") or []),
                dumps(refs.get("decision_refs") or []),
                dumps(refs.get("claim_refs") or []),
                dumps(refs.get("source_refs") or []),
                stamp,
            ),
        )
    return message_id


def list_messages(store: Store, session_id: str, limit: int = 40) -> list:
    rows = store.query(
        """SELECT * FROM agent_message WHERE session_id = ?
           ORDER BY created_at DESC, id DESC LIMIT ?""",
        (session_id, limit),
    )
    rows = list(reversed(rows))
    for row in rows:
        for key in ("entity_refs", "project_refs", "decision_refs", "claim_refs", "source_refs"):
            row[key] = loads(row.get("{0}_json".format(key)), [])
    return rows


def recent_messages(store: Store, session_id: str, limit: int = 12) -> list:
    """返回最近若干轮，供主模型保持会话连续性。

    和 list_messages 不同，这里先从尾部截取，再恢复时间正序。
    """
    rows = store.query(
        """SELECT * FROM agent_message WHERE session_id = ?
           ORDER BY created_at DESC, id DESC LIMIT ?""",
        (session_id, max(1, min(int(limit), 30))),
    )
    rows = list(reversed(rows))
    return [
        {
            "role": row.get("role") or "user",
            "content": row.get("content") or "",
            "skill": row.get("skill") or "",
            "domain": row.get("domain") or "GENERAL",
        }
        for row in rows
    ]


def add_activity(store: Store, **fields) -> dict:
    summary = fields.get("summary") or ""
    lowered = summary.lower()
    if "chain_of_thought" in lowered or "chain-of-thought" in lowered:
        raise ValueError("activity 只记执行轨迹")
    metadata = {
        key: value for key, value in dict(fields.get("metadata") or {}).items()
        if key not in _HIDDEN
    }
    stamp = now_iso()
    with store.connect() as conn:
        activity_id = _ids(conn, "agent_activity", "AA", 1)[0]
        conn.execute(
            """INSERT INTO agent_activity
               (id, session_id, project_id, decision_id, run_id, type, status, summary, metadata_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                activity_id, fields.get("session_id") or "", fields.get("project_id") or "",
                fields.get("decision_id") or "", fields.get("run_id") or "",
                fields.get("type") or "SKILL_SELECTED", fields.get("status") or "ok",
                summary, dumps(metadata), stamp,
            ),
        )
    rows = store.query("SELECT * FROM agent_activity WHERE id = ?", (activity_id,))
    return _activity(rows[0])


def list_activity(store: Store, session_id: str = "", project_id: str = "", limit: int = 40) -> list:
    if project_id:
        where, params = "project_id = ?", (project_id,)
    elif session_id:
        where, params = "session_id = ?", (session_id,)
    else:
        where, params = "1 = 1", ()
    rows = store.query(
        """SELECT * FROM agent_activity WHERE {0}
           ORDER BY created_at DESC, id DESC LIMIT ?""".format(where),
        params + (limit,),
    )
    rows.reverse()
    return [_activity(row) for row in rows]


def _activity(row: dict) -> dict:
    item = dict(row)
    item["metadata"] = loads(item.get("metadata_json"), {})
    return item
