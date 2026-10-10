"""Decision Card：把一条决策的全生命周期渲染成一屏可读文本。

刻意不做花哨排版 —— 这张卡的作用是让人一眼看出「事前说了什么、实际做了
什么、结果如何、错在哪一层」，以及哪些字段是用户自己写的、哪些是系统算的。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.review import gates, lifecycle, repo
from core.store import STORE, Store

_FLOW = [
    lifecycle.DRAFT,
    lifecycle.PLANNED,
    lifecycle.ACTIVE,
    lifecycle.CLOSED,
    lifecycle.REVIEW_PENDING,
    lifecycle.REVIEWED,
]


def _pct(value: Optional[float], digits: int = 2) -> str:
    return "—" if value is None else "{0:+.{1}f}%".format(float(value), digits)


def _num(value: Optional[float], digits: int = 3) -> str:
    return "—" if value is None else "{0:.{1}f}".format(float(value), digits).rstrip("0").rstrip(".")


def _rail(status: str) -> str:
    if status in (lifecycle.CANCELLED, lifecycle.EXPIRED):
        return status
    parts = []
    hit = False
    for state in _FLOW:
        if state == status:
            parts.append("[{0}]".format(state))
            hit = True
        else:
            parts.append(state if not hit else state.lower())
    return " → ".join(parts)


def build(decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    d = repo.require_decision(decision_id, store)
    ctx = repo.context(decision_id, store)
    return {
        "decision": d,
        "expectations": repo.expectations(decision_id, store),
        "plans": repo.plans(decision_id, store),
        "current_plan": repo.current_plan(decision_id, store),
        "executions": repo.executions(decision_id, store),
        "outcome": repo.get_outcome(decision_id, store),
        "reviews": repo.reviews(decision_id, store),
        "attributions": repo.attributions(decision_id, store),
        "violations": repo.violations(decision_id, store),
        "revisions": repo.revisions(decision_id, store),
        "transitions": repo.transitions_of(decision_id, store),
        "net_qty": repo.net_qty(decision_id, store),
        "next_states": lifecycle.next_states(d["status"], ctx),
    }


def render(decision_id: str, store: Store = STORE) -> str:
    c = build(decision_id, store)
    d = c["decision"]
    out: List[str] = []

    out.append("=" * 72)
    out.append(
        "{0}  {1} {2}  {3}".format(d["id"], d["code"], d["name"] or "", d["direction"])
    )
    out.append(_rail(d["status"]))
    origin = d.get("origin") or "EX_ANTE"
    out.append("origin {0}{1}".format(
        origin,
        "（事后复盘，不进 Plan Adherence）" if origin == "POST_HOC" else "（事前）",
    ))
    out.append("=" * 72)

    out.append("")
    out.append("── Thesis（事前，用户原话）")
    out.append("   {0}".format(d["thesis"] or "（空）"))
    meta = "   开仓日 {0} · 赚钱类型 {1} · 持有期 {2}".format(
        d["opened_on"], d["earning_type"] or "—", d["holding_period"] or "—"
    )
    out.append(meta)
    if d["subjective_context"] != "available":
        out.append("   [主观字段不可得：{0}]".format(d["subjective_context"]))

    out.append("")
    out.append("── Expectation（{0} 条）".format(len(c["expectations"])))
    if not c["expectations"]:
        out.append("   （无）")
    for e in c["expectations"]:
        window = "{0}→{1}".format(e["window_start"] or "?", e["window_end"] or "?")
        flag = "已确认" if int(e["user_confirmed"] or 0) else "predicate 未编译"
        out.append("   {0}  [{1}] {2}".format(e["id"], e["verdict"], e["raw_text"]))
        out.append("        窗口 {0} · 置信 {1} · {2}".format(window, e["confidence"] or "—", flag))

    out.append("")
    plan = c["current_plan"]
    out.append("── Plan（当前 v{0}，共 {1} 版）".format(
        (plan or {}).get("revision", 0), len(c["plans"])
    ))
    if not plan:
        out.append("   （无事前计划）")
    else:
        size = (
            "{0}%".format(plan["target_size_pct"])
            if plan["target_size_pct"] is not None
            else (str(plan["target_size_amount"]) if plan["target_size_amount"] is not None else "—")
        )
        out.append("   入场  {0}".format(plan["entry_rule"] or "—"))
        out.append("   规模  {0}    止损  {1}".format(size, _num(plan["stop_price"]) ))
        out.append("   失效  {0}".format(plan["invalidation"] or "—"))
        if plan["entry_window_start"] or plan["entry_window_end"]:
            out.append("   窗口  {0} → {1}".format(
                plan["entry_window_start"] or "?", plan["entry_window_end"] or "?"
            ))
        for older in c["plans"]:
            if older["superseded_by"]:
                out.append("   v{0} 已被 {1} 取代：{2}".format(
                    older["revision"], older["superseded_by"], older["reason_for_revision"] or "—"
                ))

    out.append("")
    out.append("── Execution（{0} 笔，净持仓 {1}）".format(
        len(c["executions"]), _num(c["net_qty"])
    ))
    if not c["executions"]:
        out.append("   （无）")
    for ex in c["executions"]:
        out.append(
            "   {0} {1} {2:<6} {3:<6} @ {4:<9} × {5:<10} 计划内={6}".format(
                ex["executed_on"],
                (ex["executed_at"] or "")[:5].ljust(5),
                ex["side"],
                ex["action"] or "—",
                _num(ex["price"]),
                _num(ex["qty"]),
                ex["planned"],
            )
        )

    out.append("")
    o = c["outcome"]
    out.append("── Outcome（system 算出，不可手改）")
    if not o:
        out.append("   （未计算）")
    else:
        out.append("   已实现 {0}   盈亏 {1}   持有 {2} 个交易日".format(
            _pct(o["realized_pct"]), _num(o["gross_pnl"], 2), o["holding_days"] or "—"
        ))
        out.append("   均价 买 {0} / 卖 {1}".format(_num(o["avg_entry"]), _num(o["avg_exit"])))
        out.append("   MFE {0} ({1})   MAE {2} ({3})   行情覆盖 {4}".format(
            _pct(o["mfe_pct"]), o["peak_on"] or "—",
            _pct(o["mae_pct"]), o["trough_on"] or "—",
            o["quote_coverage"],
        ))

    out.append("")
    out.append("── Process Compliance（Layer A：事实，确定性）")
    if not c["violations"]:
        out.append("   无违规")
    for v in c["violations"]:
        ack = "已确认" if int(v["acknowledged"] or 0) else "待确认"
        out.append("   [{0}] {1} · {2}".format(v["severity"].upper(), v["code"], ack))
        out.append("        {0}".format(v["detail"]))
    if c["violations"]:
        hint = gates.suggestions([v["code"] for v in c["violations"]])
        out.append("   候选原因（仅供人选，系统不自动归因）：{0}".format("、".join(hint)))

    out.append("")
    out.append("── Attribution（Layer B：原因判断，用户确认）")
    if not c["attributions"]:
        out.append("   （无）")
    for a in c["attributions"]:
        contributing = json.loads(a["contributing"] or "[]")
        mark = "✓" if int(a["user_confirmed"] or 0) else "待确认"
        out.append("   {0} primary={1} [{2}] 置信={3}".format(
            mark, a["primary_error"], "、".join(contributing) or "无", a["confidence"]
        ))
        if a["counterfactual"]:
            out.append("        反事实：{0}".format(a["counterfactual"]))

    if c["reviews"]:
        out.append("")
        out.append("── Review（{0} 次）".format(len(c["reviews"])))
        for r in c["reviews"]:
            out.append("   {0} {1}".format(r["reviewed_on"], r["id"]))
            if r["lesson"]:
                out.append("        教训：{0}".format(r["lesson"]))

    if c["revisions"]:
        out.append("")
        out.append("── Revision（原值保留，共 {0} 条）".format(len(c["revisions"])))
        for r in c["revisions"]:
            out.append("   {0} {1}: {2!r} → {3!r}  （{4}，by {5}）".format(
                r["changed_at"][:16], r["field"], r["old_value"], r["new_value"],
                r["reason"], r["changed_by"],
            ))

    out.append("")
    out.append("── 下一步")
    if not c["next_states"]:
        out.append("   终态，无后续")
    for n in c["next_states"]:
        if n["ready"]:
            out.append("   → {0}  可执行".format(n["to"]))
        else:
            out.append("   → {0}  还缺：{1}".format(n["to"], "；".join(n["missing"])))
    out.append("")
    out.append("研究框架，非投资建议。")
    return "\n".join(out)
