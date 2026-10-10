"""Decision 引用某一版 Thesis。不复制研报，也不强制每条 Decision 都有研究。"""
from __future__ import annotations

from core.review.repo import ReviewError, amend
from core.store import STORE, Store


def assert_link(project_id: str, thesis_id: str, version: int, store: Store = STORE) -> None:
    if not project_id or not thesis_id or not version:
        raise ReviewError("引用研究要同时给出 project、thesis 和 version")
    rows = store.query(
        "SELECT project_id FROM research_thesis WHERE id = ? AND version = ?",
        (thesis_id, int(version)),
    )
    if not rows or rows[0]["project_id"] != project_id:
        raise ReviewError("研究版本不存在")


def review_snapshot(decision_id: str, store: Store = STORE) -> dict:
    """复盘只并列当时版本和当前版本。是不是研究错误，由用户确认。"""
    rows = store.query(
        "SELECT research_project_id, research_thesis_id, research_thesis_version FROM decision WHERE id = ?",
        (decision_id,),
    )
    if not rows or not (rows[0].get("research_thesis_id") or ""):
        return {"attached": False, "research_error": "USER_CONFIRMS"}
    row = rows[0]
    versions = store.query(
        "SELECT version, diff_verdict FROM research_thesis WHERE id = ? ORDER BY version",
        (row["research_thesis_id"],),
    )
    current = int(versions[-1]["version"]) if versions else 0
    attached = int(row.get("research_thesis_version") or 0)
    verdict = ""
    if versions and current != attached:
        verdict = versions[-1].get("diff_verdict") or ""
    elif current and current == attached:
        verdict = "UNCHANGED"
    return {
        "attached": True,
        "project_id": row.get("research_project_id") or "",
        "thesis_id": row.get("research_thesis_id") or "",
        "decision_version": attached,
        "current_version": current,
        "diff_verdict": verdict,
        "research_error": "USER_CONFIRMS",
    }


def attach(decision_id: str, project_id: str, thesis_id: str, version: int, store: Store = STORE) -> None:
    assert_link(project_id, thesis_id, version, store)
    reason = "引用研究 {0} {1} v{2}".format(project_id, thesis_id, version)
    amend("decision", decision_id, "research_project_id", project_id, reason, store=store)
    amend("decision", decision_id, "research_thesis_id", thesis_id, reason, store=store)
    amend("decision", decision_id, "research_thesis_version", int(version), reason, store=store)
