"""Review → Research 的候选反馈；这里只提案，不修改 Research 事实。"""
from __future__ import annotations

from core.agent.personal_context import link_context
from core.agent.store import dumps, loads
from core.research.store import _ids, now_iso
from core.store import Store


def propose(
    store: Store,
    decision_id: str,
    statement: str,
    *,
    feedback_type: str = "RESEARCH_ERROR",
    evidence: list | None = None,
) -> dict:
    decisions = store.query(
        """SELECT research_project_id, research_thesis_id, research_thesis_version
           FROM decision WHERE id = ?""",
        (decision_id,),
    )
    if not decisions:
        raise ValueError("Decision 不存在")
    decision = decisions[0]
    reviews = store.query(
        "SELECT id FROM review WHERE decision_id = ? ORDER BY reviewed_on DESC, created_at DESC LIMIT 1",
        (decision_id,),
    )
    review_id = reviews[0]["id"] if reviews else ""
    existing = store.query(
        """SELECT * FROM research_feedback_candidate
           WHERE decision_id = ? AND feedback_type = ?
             AND research_thesis_id = ? AND research_thesis_version = ?""",
        (
            decision_id, feedback_type, decision.get("research_thesis_id") or "",
            int(decision.get("research_thesis_version") or 0),
        ),
    )
    if existing:
        return _row(existing[0])
    stamp = now_iso()
    with store.connect() as conn:
        feedback_id = _ids(conn, "research_feedback_candidate", "RF", 1)[0]
        conn.execute(
            """INSERT INTO research_feedback_candidate
               (id, decision_id, review_id, research_project_id, research_thesis_id,
                research_thesis_version, feedback_type, statement, evidence_json,
                status, created_at, updated_at, applied_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                feedback_id, decision_id, review_id,
                decision.get("research_project_id") or "",
                decision.get("research_thesis_id") or "",
                int(decision.get("research_thesis_version") or 0),
                feedback_type, statement.strip(), dumps(evidence or []),
                "PROPOSED", stamp, stamp, "",
            ),
        )
    project_id = decision.get("research_project_id") or ""
    if project_id:
        link_context(
            store, from_type="RESEARCH_FEEDBACK", from_id=feedback_id,
            relation="QUESTIONS_RESEARCH", to_type="RESEARCH_PROJECT", to_id=project_id,
            source="review", user_confirmed=False,
        )
    return get(store, feedback_id)


def get(store: Store, feedback_id: str) -> dict:
    rows = store.query("SELECT * FROM research_feedback_candidate WHERE id = ?", (feedback_id,))
    return _row(rows[0]) if rows else {}


def _row(row: dict) -> dict:
    item = dict(row)
    item["evidence"] = loads(item.get("evidence_json"), [])
    return item
