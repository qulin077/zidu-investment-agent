"""Recorder Eval 指标与失败分类。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

CRITICAL = (
    "symbol", "thesis", "expectation", "entry_rule",
    "invalidation", "target_size", "holding_period",
)
HALLUCINATION_FIELDS = (
    "invalidation", "target_size", "holding_period", "symbol", "entry_price",
)

TAXONOMY = (
    "OMISSION", "HALLUCINATION", "OVER_NORMALIZATION", "WRONG_INTENT",
    "WRONG_SYMBOL", "WRONG_NUMBER", "WRONG_SCOPE", "FAILED_ABSTENTION",
    "GROUNDING_FAILURE",
)


def _nonempty(value: Any) -> bool:
    return value not in (None, "", [], False)


def extracted(draft: Dict[str, Any]) -> Dict[str, Any]:
    plan = draft.get("plan") or {}
    expects = draft.get("expectations") or []
    exp = None
    if expects:
        exp = expects[0].get("raw_text") if isinstance(expects[0], dict) else None
    return {
        "symbol": (draft.get("symbol") or {}).get("value"),
        "thesis": (draft.get("thesis") or {}).get("value"),
        "expectation": exp,
        "entry_rule": (plan.get("entry_rule") or {}).get("value"),
        "invalidation": (plan.get("invalidation") or {}).get("value"),
        "target_size": (plan.get("target_size_pct") or {}).get("value"),
        "holding_period": (plan.get("holding_period") or {}).get("value"),
    }


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_case(case: Dict[str, Any], parsed: Dict[str, Any], grounding_ok: bool) -> Dict[str, Any]:
    gold = case.get("gold") or {}
    fields_gold = gold.get("fields") or {}
    must_not = list(gold.get("must_not") or [])
    missing_gold = list(gold.get("missing") or [])
    got = extracted(parsed)
    intent_gold = gold.get("intent")
    intent_got = parsed.get("intent")
    failures: List[Dict[str, Any]] = []

    crit_hit = crit_total = 0
    for key in CRITICAL:
        if key not in fields_gold:
            continue
        want = fields_gold[key]
        if want in (None, False):
            continue
        crit_total += 1
        have = got.get(key)
        if isinstance(want, (int, float)) and not isinstance(want, bool):
            if _num(have) == float(want):
                crit_hit += 1
            elif _nonempty(have):
                failures.append(_fail(case, "WRONG_NUMBER", key, have, want, parsed))
            else:
                failures.append(_fail(case, "OMISSION", key, have, want, parsed))
        elif _nonempty(have):
            if key == "symbol" and want not in (True, have, str(have)):
                failures.append(_fail(case, "WRONG_SYMBOL", key, have, want, parsed))
            else:
                crit_hit += 1
        else:
            failures.append(_fail(case, "OMISSION", key, have, want, parsed))

    extracted_n = sum(1 for k in CRITICAL if _nonempty(got.get(k)))
    unsupported = 0
    for key in CRITICAL:
        if not _nonempty(got.get(key)):
            continue
        want = fields_gold.get(key, "ABSENT")
        if want in (None, False):
            unsupported += 1
            if key in ("target_size", "invalidation", "holding_period"):
                failures.append(_fail(case, "HALLUCINATION", key, got.get(key), want, parsed))
            elif key == "target_size":
                failures.append(_fail(case, "OVER_NORMALIZATION", key, got.get(key), want, parsed))

    hall_hit = 0
    hall_denom = 0
    for key in HALLUCINATION_FIELDS:
        if key == "entry_price":
            continue
        hall_denom += 1
        forbidden = key in must_not or (key in fields_gold and fields_gold.get(key) in (None, False))
        if forbidden and _nonempty(got.get(key if key != "target_size" else "target_size")):
            hall_hit += 1
            if not any(f["field"] == key and f["type"] == "HALLUCINATION" for f in failures):
                failures.append(_fail(case, "HALLUCINATION", key, got.get(key), None, parsed))

    miss_hit = miss_total = 0
    agent_missing = parsed.get("missing_fields") or []
    for item in missing_gold:
        miss_total += 1
        if item in agent_missing:
            miss_hit += 1
        else:
            failures.append(_fail(case, "OMISSION", "missing:" + item, agent_missing, missing_gold, parsed))

    abstain_ok = None
    if gold.get("abstain") or intent_gold in ("CHITCHAT", "UNSUPPORTED"):
        abstain_ok = intent_got == intent_gold
        if not abstain_ok:
            failures.append(_fail(case, "FAILED_ABSTENTION", "intent", intent_got, intent_gold, parsed))
    elif intent_gold and intent_got != intent_gold:
        failures.append(_fail(case, "WRONG_INTENT", "intent", intent_got, intent_gold, parsed))

    if not grounding_ok:
        failures.append(_fail(case, "GROUNDING_FAILURE", "grounding", False, True, parsed))

    for field, needles in (gold.get("must_not_bind") or {}).items():
        have = got.get(field)
        if not _nonempty(have):
            continue
        text = str(have)
        for needle in needles:
            hit = False
            if field in ("target_size", "symbol") and _num(have) is not None and _num(needle) is not None:
                hit = _num(have) == _num(needle)
            if str(needle) in text or text == str(needle):
                hit = True
            if hit:
                kind = "WRONG_SYMBOL" if field == "symbol" else (
                    "WRONG_NUMBER" if field in ("target_size", "invalidation", "entry_rule") else "WRONG_SCOPE"
                )
                if field == "symbol":
                    kind = "WRONG_SYMBOL"
                elif field == "target_size" or (field == "invalidation" and str(needle).replace(".", "", 1).isdigit()):
                    kind = "WRONG_NUMBER"
                else:
                    kind = "WRONG_SCOPE"
                failures.append(_fail(case, kind, field, have, "must_not_bind:" + str(needle), parsed))
                break

    for field, needles in (gold.get("require_substrings") or {}).items():
        have = got.get(field)
        text = str(have or "")
        for needle in needles:
            if needle not in text:
                kind = "OMISSION" if not _nonempty(have) else "WRONG_SCOPE"
                failures.append(_fail(case, kind, field, have, "need:" + needle, parsed))

    tags = list(case.get("tags") or [])
    negation_error = 0
    correction_error = 0
    wrong_number_bind = 0
    wrong_symbol = 0
    kinds = {f["type"] for f in failures}
    if "negation" in tags and any(
        f["field"] == "invalidation" and f["type"] in ("HALLUCINATION", "WRONG_SCOPE", "WRONG_NUMBER")
        for f in failures
    ):
        negation_error = 1
    if "correction" in tags and any(
        f["field"] == "target_size" and f["type"] in ("WRONG_NUMBER", "HALLUCINATION")
        for f in failures
    ):
        correction_error = 1
    if any(f["type"] == "WRONG_NUMBER" for f in failures):
        wrong_number_bind = 1
    if any(f["type"] == "WRONG_SYMBOL" for f in failures):
        wrong_symbol = 1

    return {
        "id": case["id"],
        "type": case.get("type"),
        "tags": tags,
        "set": case.get("set") or "dev",
        "crit_hit": crit_hit,
        "crit_total": crit_total,
        "unsupported": unsupported,
        "extracted_n": extracted_n,
        "hall_hit": hall_hit,
        "hall_denom": hall_denom,
        "miss_hit": miss_hit,
        "miss_total": miss_total,
        "abstain_ok": abstain_ok,
        "negation_error": negation_error,
        "correction_error": correction_error,
        "wrong_number_bind": wrong_number_bind,
        "wrong_symbol": wrong_symbol,
        "failures": failures,
        "got": got,
        "intent": intent_got,
    }


def _fail(case, kind, field, got, gold, parsed) -> Dict[str, Any]:
    return {
        "id": case["id"],
        "type": kind,
        "field": field,
        "got": got,
        "gold": gold,
        "prompt_version": parsed.get("prompt_version") or "r1",
        "model_intent": parsed.get("intent"),
    }


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    crit_hit = sum(r["crit_hit"] for r in rows)
    crit_total = sum(r["crit_total"] for r in rows)
    unsupported = sum(r["unsupported"] for r in rows)
    extracted_n = sum(r["extracted_n"] for r in rows)
    hall_hit = sum(r["hall_hit"] for r in rows)
    miss_hit = sum(r["miss_hit"] for r in rows)
    miss_total = sum(r["miss_total"] for r in rows)
    abstain = [r["abstain_ok"] for r in rows if r["abstain_ok"] is not None]
    failures = [f for r in rows for f in r["failures"]]
    negation_n = sum(1 for r in rows if "negation" in (r.get("tags") or []))
    correction_n = sum(1 for r in rows if "correction" in (r.get("tags") or []))
    number_n = sum(1 for r in rows if "numbers" in (r.get("tags") or []) or r.get("wrong_number_bind"))
    return {
        "cases": len(rows),
        "critical_field_recall": round(100 * crit_hit / crit_total, 1) if crit_total else None,
        "unsupported_field_rate": round(100 * unsupported / extracted_n, 1) if extracted_n else 0.0,
        "critical_hallucination_rate": round(100 * hall_hit / max(1, sum(r["hall_denom"] for r in rows)), 1),
        "critical_hallucination_count": hall_hit,
        "missing_detection_recall": round(100 * miss_hit / miss_total, 1) if miss_total else None,
        "abstention_accuracy": round(100 * sum(1 for x in abstain if x) / len(abstain), 1) if abstain else None,
        "negation_error_count": sum(r.get("negation_error") or 0 for r in rows),
        "negation_error_rate": round(
            100 * sum(r.get("negation_error") or 0 for r in rows) / max(1, negation_n), 1
        ) if negation_n else 0.0,
        "correction_error_count": sum(r.get("correction_error") or 0 for r in rows),
        "correction_error_rate": round(
            100 * sum(r.get("correction_error") or 0 for r in rows) / max(1, correction_n), 1
        ) if correction_n else 0.0,
        "wrong_number_binding_count": sum(r.get("wrong_number_bind") or 0 for r in rows),
        "wrong_number_binding_rate": round(
            100 * sum(r.get("wrong_number_bind") or 0 for r in rows) / max(1, len(rows)), 1
        ),
        "wrong_symbol_critical_count": sum(r.get("wrong_symbol") or 0 for r in rows),
        "wrong_number_critical_count": sum(1 for r in rows if r.get("wrong_number_bind")),
        "failures": failures,
    }
