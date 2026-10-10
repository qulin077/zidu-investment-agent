"""Decision 匹配。确定性启发式，不调模型。

两层结构，顺序不能换：

  1. 硬过滤（disqualifiers）—— 结构上不可能的候选直接剔除。这一层是逻辑，
     不是打分，错了就是错了。
  2. 排序（score）—— 只对幸存者排序，给人看。

核心纪律：**幸存者 ≥ 2 就不自动绑定**，无论分差多大。score 存在的唯一目的
是把最可能的排在前面省人力，它不是概率，也不构成绑定依据。宁可多问一句，
也不要静默挂错 —— 挂错的成本是整条决策记忆被污染，问一句的成本是三秒钟。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Any, Dict, List, Optional, Tuple

from core.review import lifecycle, repo
from core.review.defs import threshold
from core.store import STORE, Store

MATCHER_VERSION = "m1"

AUTO_MATCHED = "AUTO_MATCHED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
NO_CANDIDATE = "NO_CANDIDATE"
HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
HUMAN_UNMATCHED = "HUMAN_UNMATCHED"

CLAIMABLE = (REVIEW_REQUIRED, NO_CANDIDATE)

# 只有这两个状态的 Decision 还能吸收新成交。
# CLOSED / REVIEW_PENDING / REVIEWED / CANCELLED / EXPIRED 一律不吸收：
# 已经了结或已复盘的决策再被塞进新成交，会让 outcome 和归因全部失真。
OPEN_STATUSES = (lifecycle.PLANNED, lifecycle.ACTIVE)


@dataclass
class Candidate:
    decision_id: str
    score: float
    reasons: List[str] = field(default_factory=list)

    @property
    def reason(self) -> str:
        return "；".join(self.reasons)


@dataclass
class MatchResult:
    execution_id: str
    status: str
    candidates: List[Candidate] = field(default_factory=list)
    reason: str = ""

    @property
    def chosen(self) -> Optional[str]:
        return self.candidates[0].decision_id if self.status == AUTO_MATCHED else None


def _days_between(a: str, b: str) -> Optional[int]:
    try:
        return (date_cls.fromisoformat(b[:10]) - date_cls.fromisoformat(a[:10])).days
    except (ValueError, TypeError):
        return None


def _disqualify(
    ex: Dict[str, Any], decision: Dict[str, Any], open_qty: float, n_exec: int
) -> Optional[str]:
    """返回剔除理由；None 表示这个候选留下。"""
    eps = threshold("flat_qty_epsilon", 1e-6)

    if decision["code"] != ex["code"]:
        return "标的不同"
    if (decision.get("account") or "") != (ex.get("account") or ""):
        return "账户不同"
    if decision["status"] not in OPEN_STATUSES:
        return "Decision 状态 {0} 不再吸收新成交".format(decision["status"])
    if decision.get("direction", "long") != "long":
        return "方向口径不支持"

    if ex["side"] == "SELL":
        if open_qty <= eps:
            return "该 Decision 当前无持仓，卖不出"
        if float(ex["qty"]) - open_qty > eps:
            return "卖出 {0} 超过该 Decision 持仓 {1}".format(ex["qty"], open_qty)

    # 成交日早于决策日 —— 不可能是这条决策的执行
    gap = _days_between(decision["opened_on"], ex["executed_on"])
    if gap is not None and gap < 0:
        return "成交日 {0} 早于决策日 {1}".format(ex["executed_on"], decision["opened_on"])

    if ex["side"] == "BUY" and decision["status"] == lifecycle.PLANNED and n_exec > 0:
        return "状态与执行记录不一致"
    return None


def _score(
    ex: Dict[str, Any],
    decision: Dict[str, Any],
    open_qty: float,
    n_exec: int,
    store: Store,
) -> Candidate:
    """启发式排序分。各项权重是人为设定的经验值，不是拟合出来的概率。"""
    eps = threshold("flat_qty_epsilon", 1e-6)
    score = 0.30
    reasons: List[str] = []

    # 语义契合度
    if ex["side"] == "BUY":
        if decision["status"] == lifecycle.PLANNED and n_exec == 0:
            score += 0.30
            reasons.append("PLANNED 待建仓，与首笔买入吻合")
        elif decision["status"] == lifecycle.ACTIVE:
            score += 0.15
            reasons.append("ACTIVE 持仓中，可能是加仓")
    else:
        if abs(float(ex["qty"]) - open_qty) <= eps:
            score += 0.30
            reasons.append("卖出量与持仓 {0} 完全一致，像清仓".format(open_qty))
        else:
            score += 0.15
            reasons.append("卖出量小于持仓 {0}，像减仓".format(open_qty))

    # 计划入场窗口
    plan = repo.current_plan(decision["id"], store)
    if plan:
        start = plan.get("entry_window_start") or ""
        end = plan.get("entry_window_end") or ""
        if start and end and start <= ex["executed_on"] <= end:
            score += 0.20
            reasons.append("落在计划入场窗口 {0}→{1}".format(start, end))

    # 时间邻近度：离决策日越近越可能是同一条决策的执行
    gap = _days_between(decision["opened_on"], ex["executed_on"])
    if gap is not None:
        if gap <= 3:
            score += 0.20
            reasons.append("距决策日 {0} 天".format(gap))
        elif gap <= 15:
            score += 0.10
            reasons.append("距决策日 {0} 天".format(gap))
        else:
            reasons.append("距决策日 {0} 天，偏远".format(gap))

    return Candidate(decision_id=decision["id"], score=round(min(score, 1.0), 2), reasons=reasons)


def candidates_for(execution_id: str, store: Store = STORE) -> Tuple[List[Candidate], List[str]]:
    """算候选。返回 (幸存候选按分降序, 被剔除的理由)。"""
    ex = repo.get_execution(execution_id, store)
    if ex is None:
        raise repo.ReviewError("找不到 execution：{0}".format(execution_id))

    pool = store.query(
        "SELECT * FROM decision WHERE code = ? AND status IN ({0}) ORDER BY opened_on".format(
            ",".join("?" for _ in OPEN_STATUSES)
        ),
        [ex["code"], *OPEN_STATUSES],
    )
    survivors: List[Candidate] = []
    rejected: List[str] = []
    for decision in pool:
        rows = repo.executions(decision["id"], store)
        open_qty = repo.net_qty(decision["id"], store)
        why = _disqualify(ex, decision, open_qty, len(rows))
        if why:
            rejected.append("{0}: {1}".format(decision["id"], why))
            continue
        survivors.append(_score(ex, decision, open_qty, len(rows), store))

    survivors.sort(key=lambda c: (-c.score, c.decision_id))
    return survivors, rejected


def match(execution_id: str, store: Store = STORE) -> MatchResult:
    """算一次匹配结论，不写库。"""
    survivors, rejected = candidates_for(execution_id, store)
    if not survivors:
        note = "无可用候选" + ("（已剔除：{0}）".format("；".join(rejected)) if rejected else "")
        return MatchResult(execution_id, NO_CANDIDATE, [], note)
    if len(survivors) == 1:
        only = survivors[0]
        return MatchResult(
            execution_id, AUTO_MATCHED, survivors,
            "唯一存活候选 {0}：{1}".format(only.decision_id, only.reason),
        )
    return MatchResult(
        execution_id, REVIEW_REQUIRED, survivors,
        "{0} 个候选都说得通，不自动绑定：{1}".format(
            len(survivors), "、".join(c.decision_id for c in survivors)
        ),
    )


def persist_candidates(result: MatchResult, store: Store = STORE) -> None:
    repo.clear_candidates(result.execution_id, store)
    if result.status != REVIEW_REQUIRED:
        return
    stamp = repo.now()
    with store.connect() as conn:
        for rank, cand in enumerate(result.candidates, start=1):
            conn.execute(
                "INSERT INTO match_candidate (execution_id, decision_id, rank, score,"
                " reason, computed_at, matcher_version) VALUES (?,?,?,?,?,?,?)",
                (result.execution_id, cand.decision_id, rank, cand.score,
                 cand.reason, stamp, MATCHER_VERSION),
            )


def apply_match(result: MatchResult, store: Store = STORE) -> MatchResult:
    """把结论写库。只有 AUTO_MATCHED 会真的绑定。"""
    if result.status == AUTO_MATCHED and result.chosen:
        repo.attach_execution(
            result.execution_id, result.chosen, changed_by="system",
            match_status=AUTO_MATCHED, match_reason=result.reason,
            matcher_version=MATCHER_VERSION, store=store,
        )
    else:
        repo.record_match_status(
            result.execution_id, result.status, "system", result.reason,
            MATCHER_VERSION, store,
        )
        persist_candidates(result, store)
    return result


def confirm(
    execution_id: str,
    decision_id: str,
    operator: str = "user",
    note: str = "",
    store: Store = STORE,
) -> Dict[str, Any]:
    """人工确认归属。只有走过这里，REVIEW_REQUIRED 的 execution 才会绑定。"""
    ex = repo.get_execution(execution_id, store)
    if ex is None:
        raise repo.ReviewError("找不到 execution：{0}".format(execution_id))
    status = ex.get("match_status") or ""
    if status and status not in CLAIMABLE and status != HUMAN_UNMATCHED:
        raise repo.ReviewError(
            "{0} 当前状态是 {1}，不能再人工绑定".format(execution_id, status)
        )
    reason = "人工确认归属 {0}".format(decision_id)
    if note:
        reason += "：{0}".format(note)
    repo.attach_execution(
        execution_id, decision_id, changed_by=operator,
        match_status=HUMAN_CONFIRMED, match_reason=reason,
        matcher_version=MATCHER_VERSION, store=store,
    )
    return {"execution_id": execution_id, "decision_id": decision_id,
            "matched_by": operator, "match_status": HUMAN_CONFIRMED}


def leave_unmatched(
    execution_id: str, operator: str = "user", note: str = "", store: Store = STORE
) -> Dict[str, Any]:
    """人工判定「这笔先不挂」。也要留痕，否则下次还会重复问。"""
    repo.record_match_status(
        execution_id, HUMAN_UNMATCHED, operator,
        note or "人工判定暂不归属任何 Decision", MATCHER_VERSION, store,
    )
    repo.clear_candidates(execution_id, store)
    return {"execution_id": execution_id, "match_status": HUMAN_UNMATCHED}


def create_post_hoc(
    execution_id: str,
    thesis: str = "",
    operator: str = "user",
    store: Store = STORE,
) -> Dict[str, Any]:
    """NO_CANDIDATE / REVIEW_REQUIRED 后，人工新建一条事后复盘 Decision。

    明确标记 origin=POST_HOC：可以进 Review / Attribution，不能进 Plan Adherence。
    """
    ex = repo.get_execution(execution_id, store)
    if ex is None:
        raise repo.ReviewError("找不到 execution：{0}".format(execution_id))
    if ex.get("decision_id"):
        raise repo.ReviewError("{0} 已挂在 {1} 上".format(execution_id, ex["decision_id"]))
    status = ex.get("match_status") or ""
    if status and status not in CLAIMABLE:
        raise repo.ReviewError(
            "{0} 当前状态是 {1}，不能新建事后 Decision".format(execution_id, status)
        )

    thesis_text = (thesis or "").strip()
    did = repo.create_decision(
        code=ex["code"],
        name=ex.get("name") or "",
        thesis=thesis_text,
        opened_on=ex["executed_on"],
        account=ex.get("account") or "",
        source="user",
        created_by=operator,
        origin="POST_HOC",
        subjective_context="available" if thesis_text else "not_recorded",
        store=store,
    )
    attached = confirm(
        execution_id, did, operator=operator,
        note="事后复盘新建 Decision", store=store,
    )
    from core.review import gates
    from core.review.intake import pipeline

    transitions = pipeline._advance_safely(did, store)
    gates.run(did, store)
    pending = [
        r["id"]
        for r in store.query(
            "SELECT id FROM execution WHERE executed_on = ? AND code = ?"
            " AND IFNULL(account,'') = ? AND decision_id IS NULL"
            " AND match_status != ?",
            (ex["executed_on"], ex["code"], ex.get("account") or "", HUMAN_UNMATCHED),
        )
    ]
    rematch = match_batch(pending, store)
    for result in rematch:
        if result.chosen:
            transitions.extend(pipeline._advance_safely(result.chosen, store))
    return {
        "decision_id": did,
        "origin": "POST_HOC",
        "execution_id": execution_id,
        "match_status": attached["match_status"],
        "transitions": transitions,
        "rematch": [
            {"execution_id": m.execution_id, "status": m.status, "decision_id": m.chosen}
            for m in rematch
        ],
    }


def match_batch(execution_ids: List[str], store: Store = STORE) -> List[MatchResult]:
    """逐笔匹配并落库。顺序执行 —— 前一笔绑定会改变后一笔的持仓前提。"""
    out: List[MatchResult] = []
    for xid in execution_ids:
        ex = repo.get_execution(xid, store)
        if ex is None or ex.get("decision_id"):
            continue
        out.append(apply_match(match(xid, store), store))
    return out
