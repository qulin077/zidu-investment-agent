"""Layer A：Process Compliance。

这里回答的是「有没有遵守自己的流程」，是可复算的事实。

与 Layer B（Outcome Attribution）严格分离：
本模块不产生、也不推荐任何 error type。SIZE_EXCEEDED 是事实，
它可能来自 Sizing Error，也可能来自 Emotion Error，也可能是当时
主动改了计划而计划改得对 —— 那是人在 review 里判断的事。

闸门可随时重算：整条删除重建，只保留用户已确认过的 acknowledged 标记。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.review import repo
from core.review.defs import gate_version, threshold, violation_spec
from core.store import STORE, Store

# 这张表只是为了让「事实 → 可能的原因」这层映射显式地留在文档里，
# 供 review 时给人当候选提示。代码不读它做自动归因。
SUGGESTS_ONLY: Dict[str, List[str]] = {
    "NO_PLAN": ["PROCESS_ERROR"],
    "UNPLANNED_EXECUTION": ["EXECUTION_ERROR", "EMOTION_ERROR", "PROCESS_ERROR"],
    "SIZE_EXCEEDED": ["SIZING_ERROR", "EMOTION_ERROR", "EXECUTION_ERROR"],
    "INVALIDATION_TRIGGERED": ["RISK_CONTROL_ERROR", "EMOTION_ERROR"],
    "STOP_NOT_EXECUTED": ["RISK_CONTROL_ERROR", "EMOTION_ERROR"],
    "LATE_ENTRY": ["TIMING_ERROR", "EXECUTION_ERROR", "PROCESS_ERROR"],
}


def _violation(
    decision_id: str,
    code: str,
    detail: str,
    evidence: List[str],
    execution_id: str = "",
) -> Dict[str, Any]:
    spec = violation_spec(code)
    return {
        "decision_id": decision_id,
        "execution_id": execution_id,
        "code": code,
        "severity": spec.get("severity") or "warn",
        "detail": detail,
        "evidence": evidence,
    }


# ------------------------------------------------------------------- 各闸门


def _gate_no_plan(decision_id: str, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    if ctx["executions"] and not ctx["plans"]:
        return [
            _violation(
                decision_id,
                "NO_PLAN",
                "有 {0} 笔 execution，但没有任何事前 plan".format(len(ctx["executions"])),
                [e["id"] for e in ctx["executions"]],
            )
        ]
    return []


def _gate_unplanned(decision_id: str, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not ctx["plans"]:
        return []  # 无 plan 由 NO_PLAN 覆盖，不重复记账
    out = []
    for ex in ctx["executions"]:
        if ex.get("planned") == "no":
            out.append(
                _violation(
                    decision_id,
                    "UNPLANNED_EXECUTION",
                    "{0} {1} {2} × {3} 标记为计划外".format(
                        ex["executed_on"], ex["side"], ex["price"], ex["qty"]
                    ),
                    [ex["id"]],
                    execution_id=ex["id"],
                )
            )
    return out


def _gate_size_exceeded(decision_id: str, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan = ctx["current_plan"]
    if not plan:
        return []
    ratio = threshold("size_exceeded_ratio", 1.5)
    buys = [e for e in ctx["executions"] if e["side"] == "BUY"]
    if not buys:
        return []

    limit_pct = plan.get("target_size_pct")
    limit_amt = plan.get("target_size_amount")

    if limit_pct is not None:
        actual = sum(float(e["size_pct"]) for e in buys if e.get("size_pct") is not None)
        if actual and actual > float(limit_pct) * ratio:
            return [
                _violation(
                    decision_id,
                    "SIZE_EXCEEDED",
                    "计划仓位 {0}%，实际累计 {1}%，超过 {2}× 容忍".format(
                        limit_pct, round(actual, 2), ratio
                    ),
                    [e["id"] for e in buys],
                )
            ]
    if limit_amt is not None:
        actual_amt = sum(float(e["amount"] or 0) for e in buys)
        if actual_amt and actual_amt > float(limit_amt) * ratio:
            return [
                _violation(
                    decision_id,
                    "SIZE_EXCEEDED",
                    "计划金额 {0}，实际累计 {1}，超过 {2}× 容忍".format(
                        limit_amt, round(actual_amt, 2), ratio
                    ),
                    [e["id"] for e in buys],
                )
            ]
    return []


def _gate_late_entry(decision_id: str, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan = ctx["current_plan"]
    if not plan:
        return []
    window_end = (plan.get("entry_window_end") or "").strip()
    buys = [e for e in ctx["executions"] if e["side"] == "BUY"]
    if not window_end or not buys:
        return []
    first = buys[0]
    if first["executed_on"] > window_end:
        return [
            _violation(
                decision_id,
                "LATE_ENTRY",
                "计划入场窗口到 {0}，首笔建仓在 {1}".format(window_end, first["executed_on"]),
                [first["id"]],
                execution_id=first["id"],
            )
        ]
    return []


def _gate_stop_not_executed(
    decision_id: str, ctx: Dict[str, Any], store: Store
) -> List[Dict[str, Any]]:
    """收盘价跌破 stop_price 后，宽限期内没有任何减仓。"""
    plan = ctx["current_plan"]
    if not plan or plan.get("stop_price") is None:
        return []
    buys = [e for e in ctx["executions"] if e["side"] == "BUY"]
    if not buys:
        return []
    stop = float(plan["stop_price"])
    start = buys[0]["executed_on"]
    # 敞口窗口：已了结就到 closed_on，还拿着就一直到手上最新的行情那天。
    # 用最后一笔成交日当右边界会漏掉「买完再没动过，期间早就破位」这种情况。
    end = ctx["decision"].get("closed_on") or ""
    if not end:
        latest = store.scalar(
            "SELECT MAX(date) FROM quote_daily WHERE code = ?", (ctx["decision"]["code"],)
        )
        end = max(ctx["executions"][-1]["executed_on"], str(latest or ""))
    quotes = store.query(
        "SELECT date, close FROM quote_daily WHERE code = ? AND date BETWEEN ? AND ?"
        " ORDER BY date",
        (ctx["decision"]["code"], start, end),
    )
    breach = next(
        (q for q in quotes if q["close"] is not None and float(q["close"]) < stop), None
    )
    if not breach:
        return []
    grace = int(threshold("stop_grace_days", 1))
    after = [q["date"] for q in quotes if q["date"] > breach["date"]][:grace]
    deadline = after[-1] if after else breach["date"]
    handled = [
        e
        for e in ctx["executions"]
        if e["side"] == "SELL" and e["executed_on"] <= deadline and e["executed_on"] >= breach["date"]
    ]
    if handled:
        return []
    return [
        _violation(
            decision_id,
            "STOP_NOT_EXECUTED",
            "{0} 收盘 {1} 跌破止损 {2}，宽限 {3} 个交易日内没有减仓".format(
                breach["date"], breach["close"], stop, grace
            ),
            ["quote:{0}@{1}".format(ctx["decision"]["code"], breach["date"])],
        )
    ]


def _gate_invalidation(decision_id: str, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """失效条件是否触发只能由人标记 —— 代码读不懂「基本面破坏」这种自然语言。

    约定：用户在 execution.note 或 review 里写 `INVALIDATION_TRIGGERED` 标记。
    闸门只负责：标记存在但之后没有减仓，就记一条。
    """
    marks = [
        e
        for e in ctx["executions"]
        if "INVALIDATION_TRIGGERED" in (e.get("note") or "").upper()
    ]
    if not marks:
        return []
    first_mark = marks[0]
    sells_after = [
        e
        for e in ctx["executions"]
        if e["side"] == "SELL" and e["executed_on"] >= first_mark["executed_on"]
    ]
    if sells_after:
        return []
    return [
        _violation(
            decision_id,
            "INVALIDATION_TRIGGERED",
            "{0} 已标记失效条件触发，之后没有任何减仓".format(first_mark["executed_on"]),
            [first_mark["id"]],
            execution_id=first_mark["id"],
        )
    ]


# ------------------------------------------------------------------- 编排


def evaluate(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    """跑一遍全部闸门，只算不写。"""
    decision = repo.require_decision(decision_id, store)
    ctx = {
        "decision": decision,
        "executions": repo.executions(decision_id, store),
        "plans": repo.plans(decision_id, store),
        "current_plan": repo.current_plan(decision_id, store),
    }
    found: List[Dict[str, Any]] = []
    found += _gate_no_plan(decision_id, ctx)
    found += _gate_unplanned(decision_id, ctx)
    found += _gate_size_exceeded(decision_id, ctx)
    found += _gate_late_entry(decision_id, ctx)
    found += _gate_stop_not_executed(decision_id, ctx, store)
    found += _gate_invalidation(decision_id, ctx)
    return found


def run(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    """跑闸门并写库。重算时保留用户已确认过的 acknowledged。"""
    import json

    found = evaluate(decision_id, store)
    prior = {
        (v["code"], v["execution_id"]): int(v.get("acknowledged") or 0)
        for v in repo.violations(decision_id, store)
    }
    stamp = repo.now()
    version = gate_version()
    with store.connect() as conn:
        conn.execute("DELETE FROM process_violation WHERE decision_id = ?", (decision_id,))
        for index, item in enumerate(found, start=1):
            vid = "PV-{0}-{1}-{2:02d}".format(decision_id[2:], item["code"], index)
            conn.execute(
                "INSERT INTO process_violation (id, decision_id, execution_id, code,"
                " severity, detail, evidence, acknowledged, detected_at, gate_version, source)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,'system')",
                (
                    vid,
                    decision_id,
                    item["execution_id"],
                    item["code"],
                    item["severity"],
                    item["detail"],
                    json.dumps(item["evidence"], ensure_ascii=False),
                    prior.get((item["code"], item["execution_id"]), 0),
                    stamp,
                    version,
                ),
            )
    return repo.violations(decision_id, store)


def suggestions(codes: List[str]) -> List[str]:
    """给 review 界面的候选 error type 提示。仅供人选，不自动写入。"""
    out: List[str] = []
    for code in codes:
        for err in SUGGESTS_ONLY.get(code, []):
            if err not in out:
                out.append(err)
    return out
