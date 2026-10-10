"""标准 Demo 的验收。缺一段就失败，不把半成品当成跑通。"""
from __future__ import annotations

from typing import List

from core.research.render import loads
from core.research.types import FORBIDDEN_PHRASES
from core.store import Store


def chain_gaps(store: Store, project_id: str, plan: dict) -> List[str]:
    gaps = []
    project = store.query("SELECT * FROM research_project WHERE id = ?", (project_id,))
    if not project:
        return ["research_question"]
    question = store.query(
        "SELECT question FROM research_question WHERE project_id = ?",
        (project_id,),
    )
    text = question[0]["question"] if question else ""
    if not text or "产业链" not in text:
        gaps.append("research_question")
    task_ids = [row.get("id") for row in (plan.get("tasks") or [])]
    missing_tasks = [task_id for task_id in ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10") if task_id not in task_ids]
    if missing_tasks:
        gaps.append("research_plan")
    sources = store.query("SELECT * FROM research_source WHERE project_id = ?", (project_id,))
    if len(sources) < 3 or any(not row.get("title") or not row.get("url") or not row.get("published_at") or not row.get("available_at") or not row.get("captured_at") for row in sources):
        gaps.append("sources")
    claims = store.query("SELECT * FROM research_claim WHERE project_id = ?", (project_id,))
    kinds = {row.get("claim_type") for row in claims}
    if len(claims) < 10 or not {"FACT", "ESTIMATE", "INFERENCE"} <= kinds:
        gaps.append("atomic_claims")
    evidence = store.query(
        """SELECT e.evidence_text, e.claim_id, s.body
           FROM research_evidence e
           JOIN research_claim c ON c.id = e.claim_id
           JOIN research_source s ON s.id = e.source_id
           WHERE c.project_id = ?""",
        (project_id,),
    )
    by_claim = {}
    for row in evidence:
        by_claim.setdefault(row["claim_id"], []).append(row)
        if (row.get("evidence_text") or "") not in (row.get("body") or ""):
            gaps.append("evidence")
            break
    else:
        critical = [row for row in claims if row.get("claim_type") == "FACT" and row.get("critical")]
        if not evidence or any(not by_claim.get(row["id"]) for row in critical):
            gaps.append("evidence")
    conflicts = store.query("SELECT id FROM research_conflict WHERE project_id = ?", (project_id,))
    unknowns = store.query("SELECT question FROM research_open_question WHERE project_id = ?", (project_id,))
    if not conflicts or not unknowns:
        gaps.append("conflict_or_unknown")
    nodes = store.query("SELECT id FROM research_value_chain WHERE project_id = ?", (project_id,))
    if len(nodes) < 3:
        gaps.append("value_chain")
    mapping = store.query("SELECT exposure_type FROM research_company_mapping WHERE project_id = ?", (project_id,))
    if len(mapping) < 2 or any((row.get("exposure_type") or "") == "DIRECT" for row in mapping):
        gaps.append("company_exposure")
    thesis = store.query(
        "SELECT * FROM research_thesis WHERE project_id = ? AND status = 'SAVED' ORDER BY version",
        (project_id,),
    )
    if not thesis or int(thesis[-1]["version"]) < 1 or not thesis[-1].get("as_of"):
        gaps.append("thesis_v1")
    else:
        refs = loads(thesis[-1].get("evidence_refs_json"), [])
        summary = thesis[-1].get("summary") or ""
        if not refs or not summary:
            gaps.append("thesis_v1")
        elif any(phrase in summary for phrase in FORBIDDEN_PHRASES):
            gaps.append("thesis_v1")
    return gaps
