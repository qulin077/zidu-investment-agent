"""Active Rule Reminder。只提醒，不改 Decision / 仓位 / 止损。"""
from __future__ import annotations

from typing import Any, Dict, List

from core.review.memory import fingerprint as fp
from core.review.memory import store as mstore
from core.review.memory.types import REMINDER_LIMIT
from core.review.memory.validator import MemoryError
from core.store import STORE, Store
from core.review import repo


def context_from_text(
    raw_text: str = "",
    symbol: str = "",
    earning_type: str = "",
    holding_period: str = "",
    target_size=None,
    market_context: str = "",
) -> Dict[str, Any]:
    emotion = fp.emotion_tag_from_text(raw_text, market_context)
    return {
        "raw_text": raw_text or "",
        "symbol": symbol or "",
        "earning_type": earning_type or "",
        "holding_period": holding_period or "",
        "target_size": target_size,
        "market_context": market_context or "",
        "emotion_tags": [emotion] if emotion else [],
    }


def get_relevant_active_rules(context: Dict[str, Any], store: Store = STORE) -> List[Dict[str, Any]]:
    """结构化匹配，最多 3 条。RETIRED 不提醒。"""
    scored: List[Dict[str, Any]] = []
    tags = set(context.get("emotion_tags") or [])
    for rule in mstore.active_rules(store):
        if (rule.get("status") or "") != "ACTIVE":
            continue
        scope = mstore.parse_json(rule.get("scope_json"), {}) or {}
        score = 0
        if scope.get("emotion_tag") and scope["emotion_tag"] in tags:
            score += 3
        if scope.get("symbol") and scope["symbol"] == (context.get("symbol") or ""):
            score += 2
        if scope.get("earning_type") and scope["earning_type"] == (context.get("earning_type") or ""):
            score += 1
        if scope.get("market_context") and scope["market_context"] in (context.get("market_context") or ""):
            score += 1
        # 新 Decision 还没有 violation：不能只靠 SIZE_EXCEEDED 全员弹窗。
        if score <= 0:
            continue
        evidence = fp.loads_list(rule.get("evidence_decision_ids"))
        why = (
            "这条提醒来自你确认过的规则 {0}。它来自 {1} 条历史 Decision：{2}。当前规则：{3}"
            .format(
                rule["id"],
                rule.get("evidence_count") or len(evidence),
                " / ".join(evidence) or "（无）",
                rule.get("rule_text") or "",
            )
        )
        if not evidence:
            continue
        scored.append({
            "rule": rule,
            "score": score,
            "why": why,
            "evidence_decision_ids": evidence,
        })
    scored.sort(key=lambda x: (-x["score"], x["rule"]["id"]))
    return scored[:REMINDER_LIMIT]


def issue_for_new_decision(
    decision_id: str,
    raw_text: str,
    parsed: Any = None,
    store: Store = STORE,
) -> List[Dict[str, Any]]:
    symbol = ""
    earning = ""
    holding = ""
    size = None
    market = ""
    if parsed is not None:
        symbol = str(getattr(getattr(parsed, "symbol", None), "value", None) or "")
        market = str(getattr(getattr(parsed, "market_context", None), "value", None) or "")
        plan = getattr(parsed, "plan", None)
        if plan is not None:
            holding = str(getattr(getattr(plan, "holding_period", None), "value", None) or "")
            size = getattr(getattr(plan, "target_size_pct", None), "value", None)
    ctx = context_from_text(raw_text, symbol, earning, holding, size, market)
    matched = get_relevant_active_rules(ctx, store)
    out = []
    for item in matched:
        rid = mstore.next_reminder_id(store)
        row = {
            "id": rid,
            "decision_id": decision_id,
            "rule_id": item["rule"]["id"],
            "why": item["why"],
            "evidence_decision_ids": fp.dumps(item["evidence_decision_ids"]),
            "created_at": repo.now(),
            "feedback": "",
            "feedback_at": "",
        }
        mstore.insert("memory_reminder", row, store)
        try:
            from core.review.memory.applicability import upsert
            upsert(item["rule"]["id"], decision_id, store)
        except Exception:  # noqa: BLE001
            pass
        try:
            from core.product.events import emit
            emit("RULE_SHOWN", "rule", item["rule"]["id"], source="reminder",
                 metadata={"decision_id": decision_id}, store=store)
            emit("REMINDER_SHOWN", "memory_reminder", rid, source="reminder",
                 metadata={"decision_id": decision_id, "rule_id": item["rule"]["id"]}, store=store)
        except Exception:  # noqa: BLE001
            pass
        out.append({
            "id": rid,
            "rule_id": item["rule"]["id"],
            "rule_text": item["rule"]["rule_text"],
            "why": item["why"],
            "evidence_decision_ids": item["evidence_decision_ids"],
            "target_size_unchanged": True,
        })
    return out


def reminders_for_decision(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    rows = mstore.reminders_for(decision_id, store)
    out = []
    for row in rows:
        rule = mstore.get_rule(row["rule_id"], store) or {}
        out.append({
            **row,
            "rule_text": rule.get("rule_text") or "",
            "rule_status": rule.get("status") or "",
            "evidence_decision_ids": fp.loads_list(row.get("evidence_decision_ids")),
        })
    return out


def feedback(reminder_id: str, value: str, store: Store = STORE) -> Dict[str, Any]:
    if value not in ("RELEVANT", "NOT_RELEVANT"):
        raise MemoryError("feedback 只能是 RELEVANT / NOT_RELEVANT")
    row = mstore.get_reminder(reminder_id, store)
    if row is None:
        raise MemoryError("找不到 reminder {0}".format(reminder_id))
    mstore.update("memory_reminder", reminder_id, {
        "feedback": value,
        "feedback_at": repo.now(),
    }, store)
    try:
        from core.product.events import emit
        emit(
            "REMINDER_RELEVANT" if value == "RELEVANT" else "REMINDER_NOT_RELEVANT",
            "memory_reminder", reminder_id, source="user", store=store,
        )
    except Exception:  # noqa: BLE001
        pass
    return mstore.get_reminder(reminder_id, store) or {}
