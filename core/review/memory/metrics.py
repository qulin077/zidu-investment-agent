"""P1.4 四个产品指标。不和 PnL 挂钩。"""
from __future__ import annotations

from typing import Any, Dict, List

from core.review.memory import fingerprint as fp
from core.review.memory import store as mstore
from core.store import STORE, Store


def _rate(num: int, den: int):
    if den <= 0:
        return None
    return round(num / den, 4)


def product_metrics(store: Store = STORE) -> Dict[str, Any]:
    mistakes = mstore.list_mistakes(store)
    patterns = mstore.list_patterns(store)
    reviewed = store.query("SELECT id, status FROM decision WHERE status = 'REVIEWED'")
    confirmed_patterns = [p for p in patterns if p.get("status") == "CONFIRMED"]
    confirmed_keys = {p["pattern_key"] for p in confirmed_patterns}
    confirmed_at = {p["id"]: p.get("confirmed_at") or "" for p in confirmed_patterns}

    repeated = 0
    related_reviewed = 0
    error_types = {(p["pattern_key"].split("|") or [""])[0] for p in confirmed_patterns}
    if error_types:
        related_reviewed = 0
        for row in reviewed:
            attrs = store.query(
                "SELECT primary_error, user_confirmed FROM attribution WHERE decision_id = ?",
                (row["id"],),
            )
            confirmed = [a for a in attrs if int(a.get("user_confirmed") or 0)]
            if confirmed and (confirmed[-1].get("primary_error") or "") in error_types:
                related_reviewed += 1
    for m in mistakes:
        pat = mstore.pattern_by_key(m["pattern_key"], store)
        if not pat or pat.get("status") != "CONFIRMED":
            continue
        if (m.get("created_at") or "") > (pat.get("confirmed_at") or ""):
            repeated += 1

    rules = mstore.list_rules(store=store)
    active = [r for r in rules if r.get("status") == "ACTIVE"]
    shown = [r for r in rules if r.get("status") in ("PROPOSED", "ACTIVE", "REJECTED")]
    accepted = [r for r in rules if r.get("status") == "ACTIVE"]
    retired = [r for r in rules if r.get("status") == "RETIRED"]

    confirmed_vios = 0
    unconfirmed_vios = 0
    relevant_decisions = 0
    from core.review.memory import applicability as rule_app
    for rule in active:
        vios = mstore.violations_of(rule["id"], store)
        confirmed_vios += sum(1 for v in vios if int(v.get("user_confirmed") or 0))
        unconfirmed_vios += sum(1 for v in vios if not int(v.get("user_confirmed") or 0))
        since = rule.get("confirmed_at") or ""
        for row in reviewed:
            d = store.query("SELECT created_at FROM decision WHERE id = ?", (row["id"],))
            created = (d[0].get("created_at") if d else "") or ""
            if since and created and created < since:
                continue
            try:
                app = rule_app.upsert(rule["id"], row["id"], store)
            except Exception:  # noqa: BLE001
                app = {"applicability": "UNKNOWN"}
            if app.get("applicability") == "APPLICABLE":
                relevant_decisions += 1

    reminders = mstore.list_reminders(store)
    with_fb = [r for r in reminders if r.get("feedback") in ("RELEVANT", "NOT_RELEVANT")]
    relevant = [r for r in with_fb if r.get("feedback") == "RELEVANT"]

    return {
        "reviewed_n": len(reviewed),
        "mistake_n": len(mistakes),
        "pattern_n": len(patterns),
        "confirmed_pattern_n": len(confirmed_patterns),
        "repeated_confirmed_mistake_count": repeated,
        "repeated_confirmed_mistake_rate": _rate(repeated, related_reviewed),
        "related_reviewed_n": related_reviewed,
        "rule_n": len(rules),
        "active_rule_n": len(active),
        "retired_rule_n": len(retired),
        "rule_acceptance_rate": _rate(len(accepted), len(shown)),
        "rule_candidates_shown": len(shown),
        "rule_violations_detected": confirmed_vios + unconfirmed_vios,
        "rule_violations_confirmed": confirmed_vios,
        "rule_violation_recurrence": _rate(confirmed_vios, relevant_decisions),
        "rule_relevant_decisions": relevant_decisions,
        "reminder_n": len(reminders),
        "reminder_feedback_n": len(with_fb),
        "memory_precision": _rate(len(relevant), len(with_fb)),
        "confirmed_pattern_keys": sorted(confirmed_keys),
    }
