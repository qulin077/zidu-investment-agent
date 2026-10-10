"""Layer 0 Facts。确定性，不用 LLM。含仓位反事实。"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from core.review import gates, lifecycle, repo
from core.review.guided.types import QUADRANTS
from core.store import STORE, Store

EMOTION_SELF = ("怕踏空", "恐慌", "不想止损", "FOMO", "情绪", "追高因为怕", "就是怕")
RESEARCH_HINTS = ("CAPEX", "产业", "景气", "逻辑", "算力")
PRICE_HINTS = ("上涨", "涨", "修复", "强于")


def _pnl_sign(outcome: Optional[Dict[str, Any]]) -> str:
    if not outcome:
        return "unknown"
    pct = outcome.get("realized_pct")
    pnl = outcome.get("gross_pnl")
    value = pct if pct is not None else pnl
    if value is None:
        return "unknown"
    if float(value) > 0:
        return "profit"
    if float(value) < 0:
        return "loss"
    return "flat"


def size_counterfactual(plan_pct, actual_pct, pnl) -> Optional[Dict[str, Any]]:
    if plan_pct in (None, "") or actual_pct in (None, "") or pnl is None:
        return None
    plan = float(plan_pct)
    actual = float(actual_pct)
    if actual == 0:
        return None
    scaled = float(pnl) * (plan / actual)
    return {
        "kind": "SIZE_SCALE",
        "plan_pct": plan,
        "actual_pct": actual,
        "actual_pnl": float(pnl),
        "scaled_pnl": round(scaled, 4),
        "statement": "若按计划仓位 {0}% 执行、其余完全不变，盈亏约 {1}".format(
            plan, round(scaled, 2),
        ),
    }


def build_context(decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    decision = repo.require_decision(decision_id, store)
    plan = repo.current_plan(decision_id, store) or {}
    executions = repo.executions(decision_id, store)
    outcome = repo.get_outcome(decision_id, store)
    expects = repo.expectations(decision_id, store)
    violations = repo.violations(decision_id, store)
    reviews = repo.reviews(decision_id, store)
    latest_review = reviews[-1] if reviews else {}
    attributions = repo.attributions(decision_id, store)
    confirmed_attr = [a for a in attributions if int(a.get("user_confirmed") or 0)]

    buys = [e for e in executions if e.get("side") == "BUY"]
    actual_size = sum(float(e["size_pct"]) for e in buys if e.get("size_pct") is not None)
    plan_size = plan.get("target_size_pct")
    codes = [v["code"] for v in violations]
    process_violated = bool(codes)
    process_tag = "violated" if process_violated else "followed"
    sign = _pnl_sign(outcome)
    coverage = (outcome or {}).get("quote_coverage") or "none"
    thesis = decision.get("thesis") or ""
    notes = " ".join(str(r.get("user_note") or "") for r in reviews)
    emotion_self = any(k in thesis or k in notes for k in EMOTION_SELF)

    evidence: List[Dict[str, str]] = []

    def ev(eid: str, statement: str) -> None:
        evidence.append({"id": eid, "statement": statement})

    ev("decision.thesis", "原想法：{0}".format(thesis or "（未记录）"))
    ev("plan.target_size", "计划仓位 {0}%".format(plan_size if plan_size is not None else "未记"))
    ev("plan.invalidation", "失效条件：{0}".format(plan.get("invalidation") or "未记"))
    ev("plan.entry_rule", "入场：{0}".format(plan.get("entry_rule") or "未记"))
    ev("actual.size", "实际累计仓位 {0}%".format(round(actual_size, 2) if actual_size else "未知"))
    if executions:
        first = executions[0]
        last = executions[-1]
        ev("execution.first", "首笔 {0} {1} {2}×{3}".format(
            first.get("executed_on"), first.get("side"), first.get("price"), first.get("qty"),
        ))
        ev("execution.last", "末笔 {0} {1} {2}×{3}".format(
            last.get("executed_on"), last.get("side"), last.get("price"), last.get("qty"),
        ))
    if outcome:
        ev("outcome.realized_pct", "实现盈亏 {0}%".format(outcome.get("realized_pct")))
        ev("outcome.coverage", "行情覆盖 {0}".format(coverage))
        if coverage == "full":
            ev("outcome.mfe", "MFE {0}%".format(outcome.get("mfe_pct")))
            ev("outcome.mae", "MAE {0}%".format(outcome.get("mae_pct")))
        else:
            ev("outcome.mfe", "MFE/MAE 因 coverage={0} 不完整，不能当完整事实".format(coverage))
    for item in expects:
        ev("expectation.{0}".format(item["id"]), "预期 {0} verdict={1}".format(
            item.get("raw_text"), item.get("verdict"),
        ))
    for item in violations:
        ev("violation.{0}".format(item["code"]), "{0}：{1}".format(item["code"], item.get("detail") or ""))

    cf = size_counterfactual(plan_size, actual_size or None, (outcome or {}).get("gross_pnl"))
    if cf:
        ev("counterfactual.size", cf["statement"])

    fact_summary = [{"statement": e["statement"], "evidence_ref": e["id"]} for e in evidence]
    quadrant = QUADRANTS.get((process_tag, sign), "未分类")

    payload = {
        "decision_id": decision_id,
        "decision": {
            "id": decision_id,
            "code": decision.get("code"),
            "name": decision.get("name"),
            "status": decision.get("status"),
            "origin": decision.get("origin"),
            "origin_status": decision.get("origin_status"),
            "thesis": thesis,
            "holding_period": decision.get("holding_period") or plan.get("holding_period"),
        },
        "plan": {
            "entry_rule": plan.get("entry_rule") or "",
            "invalidation": plan.get("invalidation") or "",
            "target_size_pct": plan_size,
            "holding_period": plan.get("holding_period") or "",
        },
        "actual": {
            "max_size_pct": actual_size or None,
            "n_executions": len(executions),
            "executions": [
                {
                    "id": e["id"], "side": e["side"], "price": e["price"], "qty": e["qty"],
                    "executed_on": e["executed_on"], "size_pct": e.get("size_pct"),
                    "planned": e.get("planned"),
                }
                for e in executions
            ],
        },
        "outcome": outcome,
        "expectations": [
            {
                "id": e["id"], "raw_text": e.get("raw_text"), "verdict": e.get("verdict"),
                "user_confirmed": int(e.get("user_confirmed") or 0),
            }
            for e in expects
        ],
        "violations": [{"code": v["code"], "detail": v.get("detail"), "severity": v.get("severity")} for v in violations],
        "violation_codes": codes,
        "process_violated": process_violated,
        "process_followed": not process_violated,
        "pnl_sign": sign,
        "quadrant": quadrant,
        "quote_coverage": coverage,
        "emotion_self_report": emotion_self,
        "research_vs_expectation": any(k in thesis for k in RESEARCH_HINTS) and any(
            any(k in str(e.get("raw_text") or "") for k in PRICE_HINTS) for e in expects
        ),
        "counterfactual": cf,
        "evidence": evidence,
        "fact_summary": fact_summary,
        "outcome_confirmed": bool(int(latest_review.get("outcome_confirmed") or 0)),
        "violations_confirmed": bool(int(latest_review.get("violations_confirmed") or 0)),
        "review_id": latest_review.get("id") or "",
        "lesson": latest_review.get("lesson") or "",
        "n_confirmed_attributions": len(confirmed_attr),
        "attribution_confirmed": bool(confirmed_attr),
        "lifecycle_status": decision.get("status"),
        "allowed_reviewed": decision.get("status") == lifecycle.REVIEW_PENDING,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    payload["context_hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    payload["gate_suggests_only"] = {k: v for k, v in gates.SUGGESTS_ONLY.items() if k in codes}
    return payload
