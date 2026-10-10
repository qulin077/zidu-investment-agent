"""Memory Eval 指标。硬门：归因泄漏 / 情绪推断 / 无证据规则。"""
from __future__ import annotations

from typing import Any, Dict, List


def score_case(case: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    gold = case.get("gold") or {}
    failures: List[str] = []

    def last_pattern():
        rows = state.get("patterns") or []
        return rows[-1] if rows else {}

    if gold.get("mistake_n") is not None and state.get("mistake_n") != gold["mistake_n"]:
        failures.append("mistake_n {0} != {1}".format(state.get("mistake_n"), gold["mistake_n"]))
    if gold.get("fact_n") is not None and state.get("fact_n") != gold["fact_n"]:
        failures.append("fact_n")
    if gold.get("pattern_status"):
        status = (last_pattern() or {}).get("status")
        if status != gold["pattern_status"] and not (gold["pattern_status"] == "CANDIDATE" and status == "CONFIRMED" and gold.get("allow_confirmed")):
            # 取匹配该 status 的任一 pattern
            if not any(p.get("status") == gold["pattern_status"] for p in (state.get("patterns") or [])):
                failures.append("pattern_status {0} != {1}".format(status, gold["pattern_status"]))
    if gold.get("no_confirmed") and any(p.get("status") == "CONFIRMED" for p in (state.get("patterns") or [])):
        failures.append("Premature Pattern")
    if gold.get("auto_confirmed") is False and any(p.get("status") == "CONFIRMED" for p in (state.get("patterns") or [])):
        failures.append("Premature Pattern")
    if gold.get("no_rule") and state.get("rule_n"):
        failures.append("rule created too early")
    if gold.get("no_pattern") and state.get("pattern_n"):
        failures.append("unexpected pattern")
    if gold.get("distinct_patterns_gte") and state.get("pattern_n", 0) < gold["distinct_patterns_gte"]:
        failures.append("same violation different attribution merged")
    if gold.get("no_fomo_pattern"):
        keys = " ".join(p.get("pattern_key") or "" for p in (state.get("patterns") or []))
        if "FOMO" in keys:
            failures.append("Emotion Inference Violation")
    if gold.get("emotion_inference") and not state.get("emotion_blocked"):
        failures.append("Emotion Inference Violation")
    if gold.get("attribution_leakage") and not state.get("leakage_blocked"):
        failures.append("Attribution Leakage")
    if gold.get("no_mistake") and state.get("mistake_n"):
        failures.append("mistake from pending/violations")
    if gold.get("validator_fail"):
        blob = " ".join(state.get("validator_issues") or [])
        for token in gold["validator_fail"]:
            if token not in blob:
                failures.append("validator missed " + token)
        if not (state.get("validator_issues") or []):
            failures.append("validator should fail")
    if gold.get("has_evidence") and not state.get("last_rule_evidence"):
        failures.append("Unsupported Rule")
    if gold.get("rule_status") and state.get("last_rule_status") != gold["rule_status"]:
        failures.append("rule_status {0} != {1}".format(state.get("last_rule_status"), gold["rule_status"]))
    if gold.get("human_confirmed_rule") and not state.get("rule_confirmed_at"):
        failures.append("rule not human confirmed")
    if gold.get("no_reminder") and state.get("reminder_n"):
        failures.append("retired rule still reminding")
    if gold.get("reminder_n") is not None and state.get("reminder_n") != gold["reminder_n"]:
        failures.append("reminder_n")
    if gold.get("reminder_has_evidence") and not state.get("reminder_has_evidence"):
        failures.append("reminder missing evidence")
    if gold.get("reminder_max") and (state.get("reminder_n") or 0) > gold["reminder_max"]:
        failures.append("too many reminders")
    if gold.get("memory_precision") is not None and state.get("memory_precision") != gold["memory_precision"]:
        failures.append("memory_precision")
    if gold.get("merge_keeps_evidence") and not state.get("merge_keeps_evidence"):
        failures.append("merge dropped evidence")
    if gold.get("confirmed_rule_violation") and not state.get("confirmed_rule_violation"):
        failures.append("rule_violation not confirmed")
    if gold.get("keep_context_diff") and not state.get("keep_context_diff"):
        failures.append("context difference dropped")
    if gold.get("confirm_pattern_fails") and not state.get("confirm_failed"):
        failures.append("single occurrence should not confirm")
    if gold.get("propose_fails") and not state.get("propose_failed"):
        failures.append("unconfirmed pattern proposed a rule")
    if gold.get("no_repeat_candidate") and (last_pattern() or {}).get("status") == "CANDIDATE":
        failures.append("dismissed candidate re-prompted without new evidence")

    return {
        "id": case["id"],
        "type": case.get("type"),
        "pass": not failures,
        "failures": failures,
        "state": {k: state.get(k) for k in (
            "mistake_n", "pattern_n", "rule_n", "last_rule_status", "reminder_n",
        )},
    }


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    fails = [r for r in rows if not r["pass"]]
    leakage = sum(1 for r in rows if any("Attribution Leakage" in x for x in r["failures"]))
    emotion = sum(1 for r in rows if any("Emotion Inference" in x for x in r["failures"]))
    unsupported = sum(1 for r in rows if any("Unsupported Rule" in x for x in r["failures"]))
    premature = sum(1 for r in rows if any("Premature Pattern" in x for x in r["failures"]))
    gate_fail = leakage > 0 or emotion > 0 or unsupported > 0
    return {
        "cases": len(rows),
        "pass": len(rows) - len(fails),
        "fail": len(fails),
        "failures": fails,
        "attribution_leakage": leakage,
        "emotion_inference_violation": emotion,
        "unsupported_rule": unsupported,
        "premature_pattern": premature,
        "gate_pass": not gate_fail and not fails,
    }
