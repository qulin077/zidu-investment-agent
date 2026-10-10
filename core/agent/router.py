"""对外仍是 route()。判断在 semantic_router。"""
from __future__ import annotations

from core.agent.semantic_router import build_plan

SKILLS = (
    "industry-research",
    "company-research",
    "event-impact",
    "candidate-discovery",
    "market-scan",
    "portfolio-monitor",
    "decision-recorder",
    "guided-review",
    "memory-query",
)


def route(message: str, session: dict | None = None, llm=None, messages: list | None = None) -> dict:
    plan = build_plan(message, session, llm=llm, messages=messages)
    entities = plan.get("entities") or []
    first = entities[0] if entities else {}
    return {
        "skill": plan.get("skill") or "",
        "domain": plan.get("domain") or "GENERAL",
        "entity": {
            "name": first.get("mention") or first.get("name") or "",
            "code": first.get("code") or "",
        },
        "confidence": plan.get("confidence") or 0,
        "reason_code": plan.get("reason_code") or "",
        "intent": plan.get("intent") or "",
        "mode": plan.get("mode") or "CHAT",
        "need_network": bool(plan.get("need_network")),
        "need_market_data": bool(plan.get("need_market_data")),
        "need_portfolio_context": bool(plan.get("need_portfolio_context")),
        "need_research_memory": bool(plan.get("need_research_memory")),
        "need_decision_memory": bool(plan.get("need_decision_memory")),
        "write_action": bool(plan.get("write_action")),
        "context_event": plan.get("context_event") or "",
        "entities": entities,
        "reply": plan.get("reply") or "",
        "journal": plan.get("journal") or {},
        "pending_draft_id": plan.get("pending_draft_id") or "",
    }
