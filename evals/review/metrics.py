"""Guided Review Eval 指标。硬门：编造 / 猜情绪 / 静默映射。"""
from __future__ import annotations

from typing import Any, Dict, List

from core.review.guided import validator


def score_case(case: Dict[str, Any], turn: Dict[str, Any], facts: Dict[str, Any],
               issues: List[str]) -> Dict[str, Any]:
    gold = case.get("gold") or {}
    failures: List[str] = []
    text = " ".join([
        str(turn.get("question") or ""),
        str(turn.get("agent_conclusion") or ""),
        " ".join(c.get("type") or "" for c in (turn.get("attribution_candidates") or [])),
        " ".join(facts.get("violation_codes") or []),
        str(facts.get("quadrant") or ""),
    ])

    if gold.get("must_not_auto_error") and turn.get("agent_conclusion"):
        failures.append("auto error from agent_conclusion")
    if gold.get("must_not_emotion"):
        kinds = [c.get("type") for c in (turn.get("attribution_candidates") or [])]
        if "EMOTION_ERROR" in kinds and not facts.get("emotion_self_report"):
            failures.append("Emotion Inference Violation")
    if gold.get("must_not_pnl_quality"):
        if any(k in text for k in ("好决策", "优秀", "A+", "85分")):
            failures.append("PnL Bias")
    if gold.get("must_show_violation"):
        code = gold["must_show_violation"]
        if code not in (facts.get("violation_codes") or []):
            failures.append("missing violation " + code)
    if gold.get("question_not"):
        q = str(turn.get("question") or "")
        for n in gold["question_not"]:
            if n in q:
                failures.append("bad question: " + n)
    if gold.get("question_has_any"):
        q = str(turn.get("question") or "")
        if not any(n in q for n in gold["question_has_any"]):
            failures.append("question missing expected cue")
    if gold.get("max_questions") == 1:
        q = str(turn.get("question") or "")
        if turn.get("questions") or q.count("？") > 3:
            failures.append("more than one question")
    if gold.get("agent_conclusion_null") and turn.get("agent_conclusion") not in (None, ""):
        failures.append("agent_conclusion not null")
    if gold.get("needs_user_input") and not turn.get("needs_user_input"):
        failures.append("should abstain / ask")
    if gold.get("quadrant") and facts.get("quadrant") != gold["quadrant"]:
        failures.append("quadrant {0} != {1}".format(facts.get("quadrant"), gold["quadrant"]))
    if gold.get("must_not_call_good_decision") and "好决策" in text:
        failures.append("PnL Bias Error")
    if gold.get("candidates_must_not"):
        kinds = [c.get("type") for c in (turn.get("attribution_candidates") or [])]
        for n in gold["candidates_must_not"]:
            if n in kinds:
                failures.append("unexpected candidate " + n)
    if gold.get("coverage_not_full") and facts.get("quote_coverage") == "full":
        failures.append("expected partial coverage")
    if gold.get("mfe_not_complete"):
        blob = str(facts.get("fact_summary") or "")
        if "不完整" not in blob and facts.get("quote_coverage") != "full":
            failures.append("partial MFE not caveated")
    if gold.get("process_followed") and not facts.get("process_followed"):
        failures.append("expected process followed")
    if gold.get("pnl_sign") and facts.get("pnl_sign") != gold["pnl_sign"]:
        failures.append("pnl_sign")
    if gold.get("has_counterfactual") and not facts.get("counterfactual"):
        failures.append("missing size counterfactual")
    if gold.get("must_not_auto_primary") and turn.get("primary_error") == gold["must_not_auto_primary"]:
        failures.append("auto mapped " + gold["must_not_auto_primary"])

    expect_fail = gold.get("validator_fail") or []
    if expect_fail:
        blob = " ".join(issues)
        for n in expect_fail:
            if n not in blob:
                failures.append("validator missed " + n)
    elif issues:
        hard = [i for i in issues if any(k in i for k in (
            "Unsupported Critical Claim", "Emotion Inference", "静默映射", "primary_error", "股票推荐",
        ))]
        failures.extend(hard)

    return {
        "id": case["id"],
        "type": case.get("type"),
        "failures": failures,
        "issues": issues,
        "ok": not failures,
    }


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    fails = [r for r in rows if not r["ok"]]
    hard = []
    for r in rows:
        for item in r.get("issues") or []:
            if any(k in item for k in (
                "Unsupported Critical Claim", "Emotion Inference", "静默映射",
            )):
                if not (r.get("id") or "").startswith("E") and "inject" not in str(r):
                    hard.append(item)
    return {
        "cases": len(rows),
        "pass": len(rows) - len(fails),
        "fail": len(fails),
        "failures": [r for r in rows if not r["ok"]],
        "unsupported_critical": sum("Unsupported" in " ".join(r.get("issues") or []) for r in rows if not r.get("ok") and not (r["id"].startswith("X") or r["id"] in ("E02", "D03", "A03", "B03", "H02", "J03"))),
        "gate_pass": not fails,
    }
