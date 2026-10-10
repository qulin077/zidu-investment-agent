"""主对话这一轮的计划。事实不放在这里。"""
from __future__ import annotations


def turn_plan(**kwargs) -> dict:
    entities = []
    for row in kwargs.get("entities") or []:
        if not isinstance(row, dict):
            continue
        mention = (row.get("mention") or row.get("name") or "").strip()
        if not mention and not row.get("code"):
            continue
        entities.append({
            "mention": mention,
            "type": row.get("type") or "company",
            "code": row.get("code") or "",
        })
    mode = kwargs.get("mode") or "CHAT"
    skill = kwargs.get("skill") or None
    if skill == "":
        skill = None
    if mode == "CHAT":
        skill = None
    return {
        "mode": mode,
        "intent": kwargs.get("intent") or ("GENERAL_CHAT" if mode == "CHAT" else ""),
        "skill": skill,
        "entities": entities,
        "need_network": bool(kwargs.get("need_network")),
        "need_market_data": bool(kwargs.get("need_market_data")),
        "need_portfolio_context": bool(kwargs.get("need_portfolio_context")),
        "need_research_memory": bool(kwargs.get("need_research_memory")),
        "need_decision_memory": bool(kwargs.get("need_decision_memory")),
        "write_action": bool(kwargs.get("write_action")),
        "confidence": float(kwargs.get("confidence") or 0),
        "reason_code": kwargs.get("reason_code") or "",
        "domain": kwargs.get("domain") or "GENERAL",
        "context_event": kwargs.get("context_event") or "",
        # 只有 conversation-first planner 会填。reply 只用于 CHAT；journal
        # 是轻量本地日记候选，不具有 Research / Decision 事实效力。
        "reply": kwargs.get("reply") or "",
        "journal": kwargs.get("journal") if isinstance(kwargs.get("journal"), dict) else {},
    }
