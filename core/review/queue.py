"""今日待复盘队列。

是 query / projection，不是表 —— Decision 的真值只有一份，队列每次现算。
这样就不存在「队列和真值不一致」这个类别的 bug。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.review import lifecycle, repo
from core.store import STORE, Store

# 上队列的理由。按紧急程度排序，一条 Decision 可能命中多条。
POSITION_CLOSED = "POSITION_CLOSED"
UNPLANNED_EXECUTION = "UNPLANNED_EXECUTION"
SIZE_EXCEEDED = "SIZE_EXCEEDED"
MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
NO_DECISION = "NO_DECISION"

_REASON_RANK = {
    POSITION_CLOSED: 0,
    MANUAL_REVIEW_REQUIRED: 1,
    UNPLANNED_EXECUTION: 2,
    SIZE_EXCEEDED: 3,
    NO_DECISION: 4,
}

# 违规码里哪些直接构成上队列的理由
_VIOLATION_REASONS = {UNPLANNED_EXECUTION, SIZE_EXCEEDED}


@dataclass
class QueueItem:
    decision_id: str
    symbol: str
    status: str
    today_execution_count: int
    realized_pnl: Optional[float]
    process_violation_count: int
    coverage: str
    review_reason: List[str] = field(default_factory=list)
    account: str = ""
    name: str = ""
    detail: str = ""

    @property
    def rank(self) -> int:
        return min((_REASON_RANK.get(r, 9) for r in self.review_reason), default=9)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "symbol": self.symbol,
            "name": self.name,
            "account": self.account,
            "status": self.status,
            "today_execution_count": self.today_execution_count,
            "realized_pnl": self.realized_pnl,
            "process_violation_count": self.process_violation_count,
            "coverage": self.coverage,
            "review_reason": self.review_reason,
            "detail": self.detail,
        }


def _today_exec_count(decision_id: str, day: str, store: Store) -> int:
    return int(
        store.scalar(
            "SELECT COUNT(*) FROM execution WHERE decision_id = ? AND executed_on = ?",
            (decision_id, day),
        )
        or 0
    )


def _quote_coverage(decision_id: str, code: str, day: str, store: Store) -> str:
    """优先用 outcome 算好的覆盖度；没有 outcome 就看当天有没有行情。"""
    row = repo.get_outcome(decision_id, store)
    if row:
        return row["quote_coverage"]
    hit = store.scalar(
        "SELECT COUNT(*) FROM quote_daily WHERE code = ? AND date = ?", (code, day)
    )
    return "full" if int(hit or 0) else "none"


def build(day: str, store: Store = STORE) -> List[QueueItem]:
    """当天的待复盘队列。"""
    items: List[QueueItem] = []

    touched = [
        r["decision_id"]
        for r in store.query(
            "SELECT DISTINCT decision_id FROM execution"
            " WHERE executed_on = ? AND decision_id IS NOT NULL",
            (day,),
        )
    ]
    pending = [
        r["id"]
        for r in store.query(
            "SELECT id FROM decision WHERE status = ?", (lifecycle.REVIEW_PENDING,)
        )
    ]
    for decision_id in dict.fromkeys(touched + pending):
        d = repo.require_decision(decision_id, store)
        violations = repo.violations(decision_id, store)
        reasons: List[str] = []
        if d["status"] == lifecycle.REVIEW_PENDING:
            reasons.append(POSITION_CLOSED)
        for v in violations:
            if v["code"] in _VIOLATION_REASONS and v["code"] not in reasons:
                reasons.append(v["code"])
        if not reasons:
            continue

        outcome = repo.get_outcome(decision_id, store)
        items.append(
            QueueItem(
                decision_id=decision_id,
                symbol=d["code"],
                name=d["name"],
                account=d.get("account") or "",
                status=d["status"],
                today_execution_count=_today_exec_count(decision_id, day, store),
                realized_pnl=(outcome or {}).get("gross_pnl"),
                process_violation_count=len(violations),
                coverage=_quote_coverage(decision_id, d["code"], day, store),
                review_reason=reasons,
                detail=(violations[0]["detail"] if violations else ""),
            )
        )

    # 当天未归属的成交：按标的聚合成一条，提示「暂无 Decision」
    orphans = store.query(
        "SELECT * FROM execution WHERE executed_on = ? AND decision_id IS NULL"
        " AND match_status != 'HUMAN_UNMATCHED'"
        " ORDER BY code, executed_at",
        (day,),
    )
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for row in orphans:
        by_symbol.setdefault("{0}|{1}".format(row["code"], row.get("account") or ""), []).append(row)

    for key, rows in by_symbol.items():
        code, _, account = key.partition("|")
        needs_human = any(r["match_status"] == "REVIEW_REQUIRED" for r in rows)
        reason = MANUAL_REVIEW_REQUIRED if needs_human else NO_DECISION
        n_cand = sum(len(repo.candidates_of(r["id"], store)) for r in rows)
        items.append(
            QueueItem(
                decision_id="",
                symbol=code,
                name=rows[0]["name"],
                account=account,
                status="—",
                today_execution_count=len(rows),
                realized_pnl=None,
                process_violation_count=0,
                coverage=_quote_coverage("", code, day, store),
                review_reason=[reason],
                detail=(
                    "{0} 个候选待人工选择".format(n_cand) if needs_human else "没有可用候选 Decision"
                ),
            )
        )

    items.sort(key=lambda i: (i.rank, i.symbol))
    return items


def as_dicts(day: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return [i.as_dict() for i in build(day, store)]
