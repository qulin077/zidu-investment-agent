"""主对话右侧的上下文。只读已有的事实，不新造一套。"""
from __future__ import annotations

from datetime import date

from core.agent.artifacts import latest
from core.agent.journal import list_entries
from core.agent.goals import list_goals
from core.agent.prompts import INVESTMENT_AGENT_PROMPT_VERSION
from core.agent.personal_context import get_strategy, list_strategies, shared_kernel
from core.agent.runtime import health
from core.agent.store import list_activity
from core.research.sessions import get_session as research_session
from core.store import Store


def panel(store: Store, session: dict) -> dict:
    summary = session.get("summary") or {}
    research_id = summary.get("research_session_id") or ""
    research = research_session(store, research_id) if research_id else {}
    body = (research or {}).get("summary") or {}
    gaps = list(body.get("open_questions") or [])
    project_id = session.get("active_project_id") or ""
    project_rows = store.query(
        "SELECT id, strategy_id FROM research_project WHERE id = ?", (project_id,)
    ) if project_id else []
    project_strategy_id = (project_rows[0].get("strategy_id") or "") if project_rows else ""
    project_strategy = get_strategy(store, project_strategy_id) if project_strategy_id else {}
    goal_id = session.get("active_goal_id") or ""
    goals = list_goals(store)
    active_goal = next((row for row in goals if row["id"] == goal_id), goals[0] if goals else {})
    today_journal = list_entries(store, day=date.today().isoformat(), session_id=session.get("id") or "", limit=5)
    kernel = shared_kernel(store, session)
    return {
        "session_id": session.get("id") or "",
        "domain": session.get("current_domain") or "GENERAL",
        "active_goal": active_goal,
        "active_strategy": kernel.get("strategy") or {},
        "strategies": list_strategies(store),
        "active_workflow": kernel.get("workflow") or {},
        "personal_memory": (kernel.get("memory") or [])[:8],
        "goals": goals,
        "active_project": {
            "id": project_id,
            "title": (research or {}).get("title") or summary.get("entity_name") or "",
            "thesis": summary.get("thesis_label") or "",
            "open_question": gaps[0] if gaps else "",
            "research_session_id": research_id,
            "strategy": {
                "id": project_strategy.get("id") or "",
                "name": project_strategy.get("name") or "",
                "time_horizon": project_strategy.get("time_horizon") or "",
                "style": project_strategy.get("style") or "",
            },
        },
        "open_decisions": store.query(
            """SELECT id, name, code, status FROM decision
               WHERE status IN ('DRAFT', 'PLANNED', 'ACTIVE')
               ORDER BY opened_on DESC LIMIT 5"""
        ),
        "pending_reviews": store.query(
            """SELECT id, name, code, status FROM decision
               WHERE status = 'REVIEW_PENDING' ORDER BY opened_on DESC LIMIT 5"""
        ),
        "active_rules": store.query(
            "SELECT id, rule_text, status FROM rule WHERE status = 'ACTIVE' ORDER BY created_at DESC LIMIT 5"
        ),
        "activity": list_activity(store, session_id=session.get("id") or "", limit=24),
        "artifact": latest(store, project_id) if project_id else {},
        "prompt_version": INVESTMENT_AGENT_PROMPT_VERSION,
        "active_entity": summary.get("active_entity") or summary.get("entity_name") or "",
        "active_event": summary.get("active_event") or "",
        "active_industry": summary.get("active_industry") or "",
        "last_skill": summary.get("last_skill") or "",
        "last_intent": summary.get("last_intent") or "",
        "last_runtime": summary.get("runtime") or {},
        "open_questions": list(summary.get("open_questions") or gaps)[:6],
        "health": health(),
        "today_journal": today_journal,
    }
