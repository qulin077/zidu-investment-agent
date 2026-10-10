"""Agent 产品指标。收益率不是北极星。"""
from __future__ import annotations

import json

from core.store import Store


def snapshot(store: Store) -> dict:
    messages = store.query(
        "SELECT skill, domain FROM agent_message WHERE role = 'user' ORDER BY created_at, id"
    )
    answers = store.query("SELECT content FROM agent_message WHERE role = 'assistant'")
    routes = {}
    switches = 0
    previous = ""
    for row in messages:
        skill = row.get("skill") or "none"
        routes[skill] = routes.get(skill, 0) + 1
        domain = row.get("domain") or ""
        if previous and domain and domain != previous:
            switches += 1
        previous = domain
    clarify = sum(
        1 for row in answers
        if any(token in (row.get("content") or "") for token in ("要复盘哪一笔", "要看哪一边", "你想看市场"))
    )
    total = len(messages) or 1
    goals = store.query("SELECT progress_json FROM agent_goal WHERE status = 'ACTIVE'")
    covered = 0
    for row in goals:
        try:
            progress = json.loads(row.get("progress_json") or "{}")
        except json.JSONDecodeError:
            progress = {}
        if progress.get("project_ids"):
            covered += 1
    return {
        "north_star": "skill_quality",
        "excluded": ["收益率"],
        "skill_routing": routes,
        "clarification_rate": round(clarify / total, 4),
        "cross_domain_switches": switches,
        "active_goal_count": len(goals),
        "goals_with_projects": covered,
        "manual_progress": True,
        "background_jobs": int(store.scalar("SELECT COUNT(*) FROM background_job") or 0),
    }
