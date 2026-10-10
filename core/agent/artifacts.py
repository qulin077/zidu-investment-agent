"""Artifact 是事实的可读视图。可以重做，不能当事实源。"""
from __future__ import annotations

from core.agent.store import dumps, loads
from core.research.sessions import get_session as research_session
from core.research.store import _ids, now_iso
from core.store import Store

COMPANY_SECTIONS = (
    "current_thesis",
    "business_model",
    "what_is_changing",
    "revenue_driver_tree",
    "profit_driver_tree",
    "industry_position",
    "commercial_stage",
    "financial_verification",
    "expectations",
    "variant_unknown",
    "catalysts",
    "risks",
    "invalidation",
    "monitoring",
    "evidence",
)


def company_card(summary: dict, title: str, focus: str = "") -> dict:
    claims = list(summary.get("claims") or [])
    texts = [row.get("text") or "" for row in claims if row.get("text")]
    gaps = list(summary.get("open_questions") or [])
    revenue = [text for text in texts if "收入" in text][:4]
    data = {
        "current_thesis": summary.get("draft_thesis") or "",
        "business_model": _first(texts, ("业务", "产品")) or "UNKNOWN",
        "what_is_changing": _first(texts, ("变化", "增长", "同比")) or "UNKNOWN",
        "revenue_driver_tree": revenue or ["UNKNOWN"],
        "profit_driver_tree": [text for text in texts if "毛利" in text or "利润" in text][:4] or ["UNKNOWN"],
        "industry_position": "UNKNOWN",
        "commercial_stage": "UNKNOWN",
        "financial_verification": [text for text in texts if "亿" in text][:4] or ["UNKNOWN"],
        "expectations": "UNKNOWN",
        "variant_unknown": gaps or ["UNKNOWN"],
        "catalysts": ["UNKNOWN"],
        "risks": ["UNKNOWN"],
        "invalidation": "UNKNOWN",
        "monitoring": gaps[:3] or ["UNKNOWN"],
        "evidence": [
            {"id": row.get("local_id") or row.get("id") or "", "text": row.get("text") or ""}
            for row in claims[:8]
        ],
        "focus": focus,
        "formal": False,
        "truth_store": False,
        "title": title,
    }
    return data


def rebuild(store: Store, project_id: str, focus: str = "", artifact_type: str = "COMPANY_RESEARCH_CARD") -> dict:
    summary, title, source_meta = _source_summary(store, project_id)
    data = company_card(summary, title, focus=focus)
    previous = latest(store, project_id, artifact_type)
    version = int((previous or {}).get("version") or 0) + 1
    stamp = now_iso()
    with store.connect() as conn:
        artifact_id = _ids(conn, "artifact", "AF", 1)[0]
        conn.execute(
            """INSERT INTO artifact
               (id, type, title, project_id, decision_id, version, data_json,
                truth_source, built_from_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                artifact_id, artifact_type, title or project_id, project_id, "", version,
                dumps(data), "DERIVED", dumps(source_meta), stamp,
            ),
        )
    return get_artifact(store, artifact_id)


def latest(store: Store, project_id: str, artifact_type: str = "") -> dict:
    if artifact_type:
        rows = store.query(
            """SELECT * FROM artifact WHERE project_id = ? AND type = ?
               ORDER BY version DESC, created_at DESC LIMIT 1""",
            (project_id, artifact_type),
        )
    else:
        rows = store.query(
            "SELECT * FROM artifact WHERE project_id = ? ORDER BY version DESC, created_at DESC LIMIT 1",
            (project_id,),
        )
    if not rows:
        return {}
    return _row(rows[0])


def get_artifact(store: Store, artifact_id: str) -> dict:
    rows = store.query("SELECT * FROM artifact WHERE id = ?", (artifact_id,))
    if not rows:
        return {}
    return _row(rows[0])


def overwrite_data(store: Store, artifact_id: str, data: dict) -> None:
    """测试和误操作都可能改到视图。重做时以研究会话为准，不读这里。"""
    with store.connect() as conn:
        conn.execute("UPDATE artifact SET data_json = ? WHERE id = ?", (dumps(data), artifact_id))


def _source_summary(store: Store, project_id: str):
    row = research_session(store, project_id)
    if row:
        summary = row.get("summary") or {}
        return summary, row.get("title") or row.get("primary_entity_name") or project_id, _source_meta(row, summary, project_id)
    found = store.query(
        "SELECT id FROM research_session WHERE project_id = ? ORDER BY updated_at DESC LIMIT 1",
        (project_id,),
    )
    if not found:
        return {}, project_id, {"project_id": project_id, "research_session_id": ""}
    row = research_session(store, found[0]["id"])
    summary = (row or {}).get("summary") or {}
    return summary, (row or {}).get("title") or project_id, _source_meta(row or {}, summary, project_id)


def _row(row: dict) -> dict:
    item = dict(row)
    item["data"] = loads(item.get("data_json"), {})
    item["built_from"] = loads(item.get("built_from_json"), {})
    return item


def _source_meta(row: dict, summary: dict, project_id: str) -> dict:
    return {
        "project_id": project_id,
        "research_session_id": row.get("id") or "",
        "run_id": row.get("last_run_id") or "",
        "claim_refs": [
            item.get("local_id") or item.get("id") or ""
            for item in (summary.get("claims") or []) if item.get("local_id") or item.get("id")
        ],
        "source_refs": [
            item.get("url") or item.get("path") or ""
            for item in (summary.get("sources") or []) if item.get("url") or item.get("path")
        ],
    }


def _first(texts, tokens) -> str:
    for text in texts:
        if any(token in text for token in tokens):
            return text
    return ""
