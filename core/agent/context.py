"""按这一句话装配上下文。不把全部聊天、全部成交或其他研究塞进去。"""
from __future__ import annotations

from core.agent.personal_context import links_for, shared_kernel
from core.agent.store import get_session
from core.research.sessions import get_session as research_session
from core.store import Store


def assemble(store: Store, session: dict, routed: dict, message: str = "") -> dict:
    summary = dict(session.get("summary") or {})
    domain = routed.get("domain") or "GENERAL"
    skill = routed.get("skill") or ""
    kernel = shared_kernel(store, session)
    loaded = ["session_summary", "shared_kernel", "active_workflow"]
    skipped = ["full_chat"]
    packet = {
        "summary": {
            "entity_name": summary.get("entity_name") or "",
            "last_skill": summary.get("last_skill") or "",
            "research_session_id": summary.get("research_session_id") or "",
            "thesis_label": summary.get("thesis_label") or "",
        },
        "goals": _goal_titles(store),
        "messages": [],
        "shared": {
            "strategy": kernel.get("strategy") or {},
            "memory": kernel.get("memory") or [],
            "active_rules": kernel.get("active_rules") or [],
            "confirmed_patterns": kernel.get("confirmed_patterns") or [],
        },
        "workflow": kernel.get("workflow") or {},
    }
    if skill in ("company-research", "industry-research") or domain == "RESEARCH":
        loaded.extend(["active_project", "thesis", "relevant_claims", "open_questions", "latest_run"])
        skipped.extend(["all_trades", "other_research", "decision_plans"])
        packet.update(_research_slice(store, summary))
    elif skill == "guided-review" or domain == "REVIEW":
        loaded.extend(["decision", "plan", "execution", "review", "active_rules"])
        skipped.extend(["full_research", "other_research"])
        packet.update(_decision_slice(store, routed, message, session))
    elif skill == "memory-query":
        loaded.extend(["patterns", "rules"])
        skipped.extend(["full_research", "all_trades", "other_research"])
        packet["patterns"] = _patterns(store)
        packet["rules"] = _rules(store)
    elif skill == "decision-recorder":
        loaded.extend(["active_project", "thesis_ref", "active_rules"])
        skipped.extend(["full_research", "all_trades"])
        packet["thesis_label"] = summary.get("thesis_label") or ""
        packet["rules"] = _rules(store)
        research = _research_head(store, summary)
        packet["project_title"] = research.get("title") or summary.get("entity_name") or ""
    else:
        skipped.extend(["full_research", "all_trades"])
    return {"loaded": loaded, "skipped": skipped, "packet": packet}


def _goal_titles(store: Store) -> list:
    rows = store.query(
        "SELECT id, title, goal_type, status FROM agent_goal WHERE status = 'ACTIVE' ORDER BY created_at"
    )
    return [{"id": row["id"], "title": row["title"], "goal_type": row["goal_type"]} for row in rows]


def _research_head(store: Store, summary: dict) -> dict:
    session_id = summary.get("research_session_id") or ""
    if not session_id:
        return {}
    row = research_session(store, session_id)
    return row or {}


def _research_slice(store: Store, summary: dict) -> dict:
    row = _research_head(store, summary)
    body = (row or {}).get("summary") or {}
    claims = []
    for item in (body.get("claims") or [])[:8]:
        claims.append({
            "id": item.get("local_id") or item.get("id") or "",
            "text": item.get("text") or "",
        })
    project_id = (row or {}).get("project_id") or (row or {}).get("id") or summary.get("research_session_id") or ""
    project_rows = store.query(
        "SELECT id, title, industry, scope, status, strategy_id FROM research_project WHERE id = ?",
        (project_id,),
    ) if project_id else []
    project = dict(project_rows[0]) if project_rows else {}
    return {
        "project": {
            "id": project_id,
            "title": (row or {}).get("title") or summary.get("entity_name") or "",
            "industry": project.get("industry") or "",
            "scope": project.get("scope") or "",
            "strategy_id": project.get("strategy_id") or "",
        },
        "thesis": (body.get("draft_thesis") or "")[:500],
        "claims": claims,
        "open_questions": list(body.get("open_questions") or [])[:6],
        "latest_run_id": (row or {}).get("last_run_id") or "",
        "context_links": links_for(store, "RESEARCH_PROJECT", project_id) if project_id else [],
    }


def _decision_slice(store: Store, routed: dict, message: str, session: dict) -> dict:
    decision = _match_decision(store, routed, message, session)
    if not decision:
        return {"decision": None, "plan": None, "executions": [], "review": None, "rules": _rules(store)}
    plans = store.query(
        "SELECT id, decision_id, target_size_pct, add_rule, stop_rule FROM plan WHERE decision_id = ? ORDER BY revision DESC LIMIT 1",
        (decision["id"],),
    )
    executions = store.query(
        "SELECT id, side, qty, price, note FROM execution WHERE decision_id = ? ORDER BY executed_on DESC LIMIT 5",
        (decision["id"],),
    )
    reviews = store.query(
        "SELECT id, lesson, user_note FROM review WHERE decision_id = ? ORDER BY reviewed_on DESC LIMIT 1",
        (decision["id"],),
    )
    return {
        "decision": {
            "id": decision["id"],
            "name": decision.get("name") or "",
            "status": decision.get("status") or "",
            "research_thesis_id": decision.get("research_thesis_id") or "",
            "research_thesis_version": decision.get("research_thesis_version") or 0,
        },
        "plan": dict(plans[0]) if plans else None,
        "executions": [dict(row) for row in executions],
        "review": dict(reviews[0]) if reviews else None,
        "rules": _rules(store),
        "research_context": _decision_research_context(store, decision),
        "context_links": links_for(store, "DECISION", decision["id"]),
    }


def _decision_research_context(store: Store, decision: dict) -> dict:
    project_id = decision.get("research_project_id") or ""
    thesis_id = decision.get("research_thesis_id") or ""
    version = int(decision.get("research_thesis_version") or 0)
    if not project_id or not thesis_id or not version:
        return {"attached": False, "entry": None, "current": None}
    entry_rows = store.query(
        """SELECT id, project_id, version, summary, diff_verdict, as_of
           FROM research_thesis WHERE id = ? AND version = ?""",
        (thesis_id, version),
    )
    current_rows = store.query(
        """SELECT id, project_id, version, summary, diff_verdict, as_of
           FROM research_thesis WHERE project_id = ?
           ORDER BY version DESC LIMIT 1""",
        (project_id,),
    )
    return {
        "attached": True,
        "project_id": project_id,
        "entry": dict(entry_rows[0]) if entry_rows else None,
        "current": dict(current_rows[0]) if current_rows else None,
    }


def _match_decision(store: Store, routed: dict, message: str, session: dict):
    active = session.get("active_decision_id") or ""
    if active:
        rows = store.query("SELECT * FROM decision WHERE id = ?", (active,))
        if rows:
            return rows[0]
    name = ((routed.get("entity") or {}).get("name") or "").strip()
    if name and name in (message or ""):
        rows = store.query(
            "SELECT * FROM decision WHERE name LIKE ? ORDER BY opened_on DESC LIMIT 1",
            ("%{0}%".format(name),),
        )
        if rows:
            return rows[0]
    return None


def _patterns(store: Store) -> list:
    return store.query(
        "SELECT id, pattern_key, summary, status FROM pattern ORDER BY created_at DESC LIMIT 8"
    )


def _rules(store: Store) -> list:
    return store.query(
        "SELECT id, rule_text, status FROM rule WHERE status = 'ACTIVE' ORDER BY created_at DESC LIMIT 8"
    )


def reload(store: Store, session_id: str) -> dict:
    return get_session(store, session_id)
