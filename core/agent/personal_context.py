"""Personal Agent 的共享上下文内核。

本模块只存个人化配置、工作流状态与跨领域引用；Research、Decision、Review
仍是各自事实源，不能复制到 personal_memory 里变成第二份真相。
"""
from __future__ import annotations

from typing import Optional

from core.agent.store import dumps, loads, save_session
from core.research.store import _ids, now_iso
from core.store import Store


def create_strategy(
    store: Store,
    name: str,
    *,
    description: str = "",
    time_horizon: str = "",
    style: str = "",
    research_preferences: Optional[dict] = None,
    decision_preferences: Optional[dict] = None,
    review_preferences: Optional[dict] = None,
    risk_constraints: Optional[dict] = None,
) -> dict:
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("strategy name 不能为空")
    existing = store.query("SELECT * FROM strategy_profile WHERE name = ?", (clean_name,))
    if existing:
        return _strategy(existing[0])
    stamp = now_iso()
    with store.connect() as conn:
        strategy_id = _ids(conn, "strategy_profile", "SP", 1)[0]
        conn.execute(
            """INSERT INTO strategy_profile
               (id, name, description, time_horizon, style, status,
                research_preferences_json, decision_preferences_json,
                review_preferences_json, risk_constraints_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                strategy_id, clean_name, description, time_horizon, style, "ACTIVE",
                dumps(research_preferences or {}), dumps(decision_preferences or {}),
                dumps(review_preferences or {}), dumps(risk_constraints or {}), stamp, stamp,
            ),
        )
    return get_strategy(store, strategy_id)


def get_strategy(store: Store, strategy_id: str) -> dict:
    rows = store.query("SELECT * FROM strategy_profile WHERE id = ?", (strategy_id,))
    return _strategy(rows[0]) if rows else {}


def list_strategies(store: Store, status: str = "ACTIVE") -> list:
    if status:
        rows = store.query(
            "SELECT * FROM strategy_profile WHERE status = ? ORDER BY updated_at DESC", (status,),
        )
    else:
        rows = store.query("SELECT * FROM strategy_profile ORDER BY updated_at DESC")
    return [_strategy(row) for row in rows]


def set_active_strategy(store: Store, session_id: str, strategy_id: str) -> dict:
    strategy = get_strategy(store, strategy_id)
    if not strategy or strategy.get("status") != "ACTIVE":
        raise ValueError("strategy 不存在或未启用")
    save_session(store, session_id, active_strategy_id=strategy_id)
    return strategy


def remember(
    store: Store,
    *,
    memory_type: str,
    memory_key: str,
    value,
    scope_type: str = "GLOBAL",
    scope_id: str = "",
    provenance_type: str = "USER",
    provenance_id: str = "",
    confidence: float = 1.0,
    confirmation_status: str = "EXPLICIT",
) -> dict:
    if not (memory_type or "").strip() or not (memory_key or "").strip():
        raise ValueError("memory_type 和 memory_key 不能为空")
    if confirmation_status == "INFERRED" and not provenance_id:
        raise ValueError("推断记忆必须带 provenance_id")
    stamp = now_iso()
    with store.connect() as conn:
        memory_id = _ids(conn, "personal_memory", "PM", 1)[0]
        conn.execute(
            """INSERT INTO personal_memory
               (id, memory_type, scope_type, scope_id, memory_key, value_json,
                provenance_type, provenance_id, confidence, confirmation_status,
                effective_at, superseded_by, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                memory_id, memory_type.strip(), scope_type, scope_id, memory_key.strip(),
                dumps(value if isinstance(value, dict) else {"value": value}), provenance_type, provenance_id,
                max(0.0, min(float(confidence), 1.0)), confirmation_status,
                stamp, "", stamp, stamp,
            ),
        )
        conn.execute(
            """UPDATE personal_memory SET superseded_by = ?, updated_at = ?
               WHERE scope_type = ? AND scope_id = ? AND memory_key = ?
                 AND id != ? AND superseded_by = ''""",
            (memory_id, stamp, scope_type, scope_id, memory_key.strip(), memory_id),
        )
    return get_memory(store, memory_id)


def get_memory(store: Store, memory_id: str) -> dict:
    rows = store.query("SELECT * FROM personal_memory WHERE id = ?", (memory_id,))
    return _memory(rows[0]) if rows else {}


def list_memory(
    store: Store,
    *,
    scope_type: str = "",
    scope_id: str = "",
    include_inferred: bool = True,
    limit: int = 24,
) -> list:
    where = ["superseded_by = ''", "confirmation_status != 'REJECTED'"]
    params = []
    if scope_type:
        where.append("scope_type = ?")
        params.append(scope_type)
    if scope_id:
        where.append("scope_id = ?")
        params.append(scope_id)
    if not include_inferred:
        where.append("confirmation_status != 'INFERRED'")
    params.append(max(1, min(int(limit), 100)))
    rows = store.query(
        "SELECT * FROM personal_memory WHERE {0} ORDER BY updated_at DESC LIMIT ?".format(
            " AND ".join(where)
        ),
        tuple(params),
    )
    return [_memory(row) for row in rows]


def start_workflow(
    store: Store,
    session_id: str,
    workflow_type: str,
    stage: str,
    **fields,
) -> dict:
    current = active_workflow(store, session_id)
    if current:
        if current.get("workflow_type") == workflow_type:
            return update_workflow(store, current["id"], stage=stage, **fields)
        complete_workflow(store, current["id"], status="PAUSED")
    stamp = now_iso()
    with store.connect() as conn:
        workflow_id = _ids(conn, "agent_workflow", "WF", 1)[0]
        conn.execute(
            """INSERT INTO agent_workflow
               (id, session_id, workflow_type, stage, status, strategy_id,
                industry_project_id, company_project_id, decision_id, review_id,
                draft_id, pending_question, state_json, created_at, updated_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                workflow_id, session_id, workflow_type, stage, "ACTIVE",
                fields.get("strategy_id") or "", fields.get("industry_project_id") or "",
                fields.get("company_project_id") or "", fields.get("decision_id") or "",
                fields.get("review_id") or "", fields.get("draft_id") or "",
                fields.get("pending_question") or "", dumps(fields.get("state") or {}),
                stamp, stamp, "",
            ),
        )
    return get_workflow(store, workflow_id)


def active_workflow(store: Store, session_id: str) -> dict:
    rows = store.query(
        """SELECT * FROM agent_workflow WHERE session_id = ? AND status = 'ACTIVE'
           ORDER BY updated_at DESC LIMIT 1""",
        (session_id,),
    )
    return _workflow(rows[0]) if rows else {}


def get_workflow(store: Store, workflow_id: str) -> dict:
    rows = store.query("SELECT * FROM agent_workflow WHERE id = ?", (workflow_id,))
    return _workflow(rows[0]) if rows else {}


def update_workflow(store: Store, workflow_id: str, **fields) -> dict:
    allowed = {
        "stage", "strategy_id", "industry_project_id", "company_project_id",
        "decision_id", "review_id", "draft_id", "pending_question",
    }
    values = {key: fields[key] for key in allowed if key in fields}
    if "state" in fields:
        values["state_json"] = dumps(fields.get("state") or {})
    if not values:
        return get_workflow(store, workflow_id)
    values["updated_at"] = now_iso()
    sql = "UPDATE agent_workflow SET {0} WHERE id = ?".format(
        ", ".join("{0} = ?".format(key) for key in values)
    )
    with store.connect() as conn:
        conn.execute(sql, tuple(values.values()) + (workflow_id,))
    return get_workflow(store, workflow_id)


def complete_workflow(store: Store, workflow_id: str, status: str = "COMPLETED") -> dict:
    if status not in ("COMPLETED", "CANCELLED", "PAUSED"):
        raise ValueError("非法 workflow 结束状态")
    stamp = now_iso()
    with store.connect() as conn:
        conn.execute(
            "UPDATE agent_workflow SET status = ?, updated_at = ?, completed_at = ? WHERE id = ?",
            (status, stamp, stamp, workflow_id),
        )
    return get_workflow(store, workflow_id)


def link_context(
    store: Store,
    *,
    from_type: str,
    from_id: str,
    relation: str,
    to_type: str,
    to_id: str,
    source: str = "system",
    user_confirmed: bool = False,
) -> dict:
    if not all((from_type, from_id, relation, to_type, to_id)):
        raise ValueError("context link 字段不能为空")
    existing = store.query(
        """SELECT * FROM context_link
           WHERE from_type = ? AND from_id = ? AND relation = ? AND to_type = ? AND to_id = ?""",
        (from_type, from_id, relation, to_type, to_id),
    )
    if existing:
        return dict(existing[0])
    stamp = now_iso()
    with store.connect() as conn:
        link_id = _ids(conn, "context_link", "CL", 1)[0]
        conn.execute(
            """INSERT INTO context_link
               (id, from_type, from_id, relation, to_type, to_id, status,
                source, user_confirmed, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                link_id, from_type, from_id, relation, to_type, to_id, "ACTIVE",
                source, int(bool(user_confirmed)), stamp,
            ),
        )
    return dict(store.query("SELECT * FROM context_link WHERE id = ?", (link_id,))[0])


def links_for(store: Store, object_type: str, object_id: str) -> list:
    return store.query(
        """SELECT * FROM context_link
           WHERE status = 'ACTIVE'
             AND ((from_type = ? AND from_id = ?) OR (to_type = ? AND to_id = ?))
           ORDER BY created_at""",
        (object_type, object_id, object_type, object_id),
    )


def shared_kernel(store: Store, session: dict) -> dict:
    strategy_id = session.get("active_strategy_id") or ""
    workflow = active_workflow(store, session.get("id") or "")
    global_memory = list_memory(store, scope_type="GLOBAL", include_inferred=True, limit=12)
    strategy_memory = (
        list_memory(store, scope_type="STRATEGY", scope_id=strategy_id, include_inferred=True, limit=12)
        if strategy_id else []
    )
    return {
        "strategy": get_strategy(store, strategy_id) if strategy_id else {},
        "workflow": workflow,
        "memory": global_memory + strategy_memory,
        "active_rules": store.query(
            "SELECT id, rule_text, scope_json FROM rule WHERE status = 'ACTIVE' ORDER BY created_at DESC LIMIT 8"
        ),
        "confirmed_patterns": store.query(
            """SELECT id, pattern_key, summary FROM pattern
               WHERE status = 'CONFIRMED' ORDER BY last_seen_at DESC, created_at DESC LIMIT 8"""
        ),
    }


def planner_state(store: Store, session: dict) -> dict:
    """给 Planner 的小状态包；不携带领域正文和全部个人记忆。"""
    kernel = shared_kernel(store, session)
    strategy = kernel.get("strategy") or {}
    workflow = kernel.get("workflow") or {}
    return {
        "active_strategy": {
            "id": strategy.get("id") or "",
            "name": strategy.get("name") or "",
            "time_horizon": strategy.get("time_horizon") or "",
            "style": strategy.get("style") or "",
        },
        "active_workflow": {
            "id": workflow.get("id") or "",
            "type": workflow.get("workflow_type") or "",
            "stage": workflow.get("stage") or "",
            "decision_id": workflow.get("decision_id") or "",
            "pending_question": workflow.get("pending_question") or "",
        },
    }


def _strategy(row: dict) -> dict:
    item = dict(row)
    for key in ("research_preferences", "decision_preferences", "review_preferences", "risk_constraints"):
        item[key] = loads(item.get("{0}_json".format(key)), {})
    return item


def _memory(row: dict) -> dict:
    item = dict(row)
    item["value"] = loads(item.get("value_json"), {})
    return item


def _workflow(row: dict) -> dict:
    item = dict(row)
    item["state"] = loads(item.get("state_json"), {})
    return item
