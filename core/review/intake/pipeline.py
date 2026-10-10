"""收盘导入编排：导入 → 去重 → 匹配 → 安全推进生命周期 → 生成队列。

生命周期推进这一步的边界写死在这里：

  可以自动      DRAFT   → ACTIVE（仅 origin=POST_HOC 且已有 execution）
                PLANNED → ACTIVE（首笔执行落地）
                ACTIVE  → CLOSED（净持仓归零）
                CLOSED  → REVIEW_PENDING（outcome 算完）
  绝不自动      → REVIEWED、Attribution、Thesis、任何用户主观内容

部分减仓不会进 CLOSED —— 净持仓不为零时 outcome.close_and_compute 直接拒绝。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.review import gates, lifecycle, matching, outcome, queue, repo
from core.review.intake.adapters import get_adapter
from core.review.intake.importer import ImportResult, import_executions
from core.store import STORE, Store


@dataclass
class IntakeReport:
    trade_date: str
    imported: Optional[ImportResult] = None
    matches: List[matching.MatchResult] = field(default_factory=list)
    transitions: List[Dict[str, Any]] = field(default_factory=list)
    queue: List[Dict[str, Any]] = field(default_factory=list)
    gated: List[str] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        by_status: Dict[str, int] = {}
        for m in self.matches:
            by_status[m.status] = by_status.get(m.status, 0) + 1
        return by_status

    def as_dict(self) -> Dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "import": self.imported.as_dict() if self.imported else None,
            "match": {
                "counts": self.counts(),
                "detail": [
                    {
                        "execution_id": m.execution_id,
                        "status": m.status,
                        "decision_id": m.chosen,
                        "reason": m.reason,
                        "candidates": [
                            {"decision_id": c.decision_id, "score": c.score,
                             "reason": c.reason}
                            for c in m.candidates
                        ],
                    }
                    for m in self.matches
                ],
            },
            "transitions": self.transitions,
            "gated_decisions": self.gated,
            "queue": self.queue,
        }


def _advance_safely(decision_id: str, store: Store) -> List[Dict[str, Any]]:
    """只走无歧义的那几步。任何需要人判断的地方停下。"""
    moved: List[Dict[str, Any]] = []
    moved.extend(repo.advance(decision_id, store=store))

    row = repo.require_decision(decision_id, store)
    # 净持仓归零才算了结；部分减仓留在 ACTIVE。
    if row["status"] == lifecycle.ACTIVE and outcome.is_flat(decision_id, store):
        outcome.close_and_compute(decision_id, changed_by="system", store=store)
        moved.append({"id": decision_id, "from": lifecycle.ACTIVE,
                      "to": lifecycle.REVIEW_PENDING, "by": "system"})
    elif row["status"] == lifecycle.CLOSED and not repo.get_outcome(decision_id, store):
        outcome.persist(decision_id, store)
        moved.append(repo.transition(decision_id, lifecycle.REVIEW_PENDING,
                                     "outcome 已算出", "system", "system", store))
    # REVIEW_PENDING → REVIEWED 永远不自动走：需要用户确认 outcome、违规和归因。
    return moved


def run(
    trade_date: str,
    source: Any = None,
    adapter: str = "csv",
    account: str = "",
    store: Store = STORE,
) -> IntakeReport:
    report = IntakeReport(trade_date=trade_date)

    if source:
        parsed = get_adapter(adapter).parse(source, account=account)
        report.imported = import_executions(parsed, trade_date=trade_date, store=store)

    # 当天所有还没归属的成交都参与匹配，不只是本次新导入的 ——
    # 昨天留下的 REVIEW_REQUIRED 也应该在今天重新给出候选。
    pending = [
        r["id"]
        for r in store.query(
            "SELECT id FROM execution WHERE executed_on = ? AND decision_id IS NULL"
            " AND match_status != 'HUMAN_UNMATCHED' ORDER BY executed_at, id",
            (trade_date,),
        )
    ]
    report.matches = matching.match_batch(pending, store)

    if source:
        _record_run(report, adapter, str(source), store)

    touched = sorted({m.chosen for m in report.matches if m.chosen})
    touched += [
        r["decision_id"]
        for r in store.query(
            "SELECT DISTINCT decision_id FROM execution"
            " WHERE executed_on = ? AND decision_id IS NOT NULL",
            (trade_date,),
        )
    ]
    for decision_id in dict.fromkeys(touched):
        report.transitions.extend(_advance_safely(decision_id, store))
        gates.run(decision_id, store)
        report.gated.append(decision_id)

    report.queue = queue.as_dicts(trade_date, store)
    try:
        from core.product.events import emit
        if report.imported:
            for xid in report.imported.inserted:
                emit("EXECUTION_IMPORTED", "execution", xid, source="intake",
                     metadata={"trade_date": trade_date}, store=store)
        for m in report.matches:
            if m.chosen:
                emit("EXECUTION_MATCHED", "execution", m.execution_id, source="intake",
                     metadata={"decision_id": m.chosen, "status": m.status}, store=store)
    except Exception:  # noqa: BLE001
        pass
    return report


def _record_run(report: IntakeReport, adapter: str, source_ref: str, store: Store) -> None:
    imported = report.imported
    if imported is None:
        return
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO intake_run (trade_date, ran_at, adapter, source_ref, rows_in,"
            " inserted, duplicate, non_trade, unparseable,"
            " auto_matched, review_required, no_candidate)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (report.trade_date, repo.now(), adapter, source_ref, imported.rows_in,
             len(imported.inserted), len(imported.duplicate),
             len(imported.non_trade), len(imported.unparseable),
             report.counts().get(matching.AUTO_MATCHED, 0),
             report.counts().get(matching.REVIEW_REQUIRED, 0),
             report.counts().get(matching.NO_CANDIDATE, 0)),
        )
