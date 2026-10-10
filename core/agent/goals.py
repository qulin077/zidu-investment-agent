"""轻量目标。只聚合进度，不调度、不提醒。"""
from __future__ import annotations

from core.agent.store import dumps, loads, save_session
from core.research.store import _ids, now_iso
from core.store import Store


def create(store: Store, title: str, goal_type: str = "RESEARCH", description: str = "",
           project_ids: list | None = None, pattern_ids: list | None = None, session_id: str = "") -> dict:
    kind = goal_type if goal_type in ("RESEARCH", "BEHAVIOR", "GENERAL") else "GENERAL"
    progress = {
        "project_ids": list(project_ids or []),
        "pattern_ids": list(pattern_ids or []),
        "manual": True,
    }
    stamp = now_iso()
    with store.connect() as conn:
        goal_id = _ids(conn, "agent_goal", "AG", 1)[0]
        conn.execute(
            """INSERT INTO agent_goal
               (id, title, goal_type, status, description, progress_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (goal_id, title.strip(), kind, "ACTIVE", description, dumps(progress), stamp, stamp),
        )
    if session_id:
        current = store.query("SELECT active_goal_id FROM agent_session WHERE id = ?", (session_id,))
        if current and not (current[0].get("active_goal_id") or ""):
            save_session(store, session_id, active_goal_id=goal_id)
    return get_goal(store, goal_id)


def get_goal(store: Store, goal_id: str) -> dict:
    rows = store.query("SELECT * FROM agent_goal WHERE id = ?", (goal_id,))
    if not rows:
        return {}
    return _row(rows[0])


def list_goals(store: Store) -> list:
    rows = store.query("SELECT * FROM agent_goal ORDER BY created_at")
    return [_row(row) for row in rows]


def _row(row: dict) -> dict:
    item = dict(row)
    item["progress"] = loads(item.get("progress_json"), {})
    return item
