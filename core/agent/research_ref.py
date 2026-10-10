"""Decision 只引用已经存在的 Thesis 版本。草稿不能冒充正式版本。"""
from __future__ import annotations

from core.policy import ALLOW, decide
from core.research.decision_link import attach, review_snapshot
from core.store import Store


def thesis_label(store: Store, name: str, research_session_id: str = "") -> str:
    label_name = name or "这项研究"
    if research_session_id:
        rows = store.query(
            "SELECT current_thesis_id, current_thesis_version, project_id FROM research_session WHERE id = ?",
            (research_session_id,),
        )
        if rows and int(rows[0].get("current_thesis_version") or 0):
            return "{0} Thesis v{1}".format(label_name, int(rows[0]["current_thesis_version"]))
        project_id = (rows[0].get("project_id") if rows else "") or ""
        if project_id:
            found = _latest_thesis(store, project_id)
            if found:
                return "{0} Thesis v{1}".format(label_name, found)
    if name:
        projects = store.query(
            "SELECT id FROM research_project WHERE title LIKE ? ORDER BY updated_at DESC LIMIT 1",
            ("%{0}%".format(name),),
        )
        if projects:
            found = _latest_thesis(store, projects[0]["id"])
            if found:
                return "{0} Thesis v{1}".format(label_name, found)
    return "{0} 研究档案（持续更新）".format(label_name)


def confirm_thesis(store: Store, decision_id: str, project_id: str, thesis_id: str, version: int) -> dict:
    """用户确认之后才挂上。自动交易和自动改仓位不走这里。"""
    if decide("attach_thesis", confirmed=True) != ALLOW:
        raise PermissionError("引用 Thesis 需要允许")
    attach(decision_id, project_id, thesis_id, int(version), store)
    return review_snapshot(decision_id, store)


def _latest_thesis(store: Store, project_id: str) -> int:
    rows = store.query(
        "SELECT version FROM research_thesis WHERE project_id = ? ORDER BY version DESC LIMIT 1",
        (project_id,),
    )
    if not rows:
        return 0
    return int(rows[0]["version"] or 0)
