"""Active Rule 对某条 Decision 是否进入 recurrence 分母。"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from core.review import repo
from core.review.memory import store as mstore
from core.store import STORE, Store

APPLICABLE = "APPLICABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"

SIZE_HINTS = ("target_size", "仓位", "扩仓", "加仓", "size")


def classify(rule: Dict[str, Any], decision_id: str, store: Store = STORE) -> Tuple[str, str]:
    if (rule.get("status") or "") == "RETIRED":
        return NOT_APPLICABLE, "RETIRED rule"
    if not decision_id:
        return UNKNOWN, "no decision"
    try:
        decision = repo.require_decision(decision_id, store)
    except Exception:  # noqa: BLE001
        return UNKNOWN, "decision missing"
    text = "{0} {1} {2}".format(
        rule.get("rule_text") or "", rule.get("trigger_text") or "", rule.get("expected_behavior") or "",
    )
    needs_size = any(h in text for h in SIZE_HINTS)
    plan = repo.current_plan(decision_id, store)
    size = None if not plan else plan.get("target_size_pct")
    if needs_size and (size is None or size == ""):
        return NOT_APPLICABLE, "Decision 没有 target_size"
    if not decision.get("code") and "symbol" in (rule.get("scope_json") or ""):
        return UNKNOWN, "symbol unknown"
    return APPLICABLE, ""


def upsert(rule_id: str, decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    rule = mstore.get_rule(rule_id, store) or {"id": rule_id, "status": "", "rule_text": ""}
    status, reason = classify(rule, decision_id, store)
    row = {
        "rule_id": rule_id,
        "decision_id": decision_id,
        "applicability": status,
        "reason": reason,
        "computed_at": repo.now(),
    }
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO rule_applicability (rule_id, decision_id, applicability, reason, computed_at)"
            " VALUES (?,?,?,?,?) ON CONFLICT(rule_id, decision_id) DO UPDATE SET"
            " applicability=excluded.applicability, reason=excluded.reason, computed_at=excluded.computed_at",
            (row["rule_id"], row["decision_id"], row["applicability"], row["reason"], row["computed_at"]),
        )
    return row


def for_rule(rule_id: str, store: Store = STORE):
    try:
        return store.query("SELECT * FROM rule_applicability WHERE rule_id = ?", (rule_id,))
    except Exception:  # noqa: BLE001
        return []
