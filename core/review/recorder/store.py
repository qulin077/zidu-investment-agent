"""recorder_input / recorder_draft 存取。原话在确认前就已经落库。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.review import repo
from core.review.recorder.types import DRAFT_STATUSES
from core.store import STORE, Store


def _next_id(prefix: str, table: str, store: Store) -> str:
    day = repo.today().replace("-", "")
    head = "{0}-{1}-".format(prefix, day)
    return "{0}{1:04d}".format(head, repo._next_seq(store, table, head))


def insert_input(
    raw_text: str,
    received_at: str,
    source: str = "web",
    mode: str = "",
    known_symbol: str = "",
    known_company: str = "",
    account: str = "",
    draft_id: str = "",
    store: Store = STORE,
) -> str:
    rid = _next_id("RI", "recorder_input", store)
    repo._insert(store, "recorder_input", {
        "id": rid,
        "raw_text": raw_text,
        "received_at": received_at,
        "source": source,
        "mode": mode or "",
        "known_symbol": known_symbol or "",
        "known_company": known_company or "",
        "account": account or "",
        "draft_id": draft_id or "",
        "created_at": received_at,
    })
    return rid


def insert_draft(
    input_event_id: str,
    raw_agent_output: str,
    parsed: Dict[str, Any],
    status: str,
    validation_status: str,
    validation_errors: List[Any],
    prompt_version: str,
    schema_version: str,
    model: str,
    temperature: float,
    origin_resolved: str = "",
    store: Store = STORE,
) -> str:
    if status not in DRAFT_STATUSES:
        raise repo.ReviewError("未知 draft status：{0}".format(status))
    did = _next_id("RD", "recorder_draft", store)
    repo._insert(store, "recorder_draft", {
        "id": did,
        "input_event_id": input_event_id,
        "raw_agent_output": raw_agent_output,
        "parsed_json": json.dumps(parsed, ensure_ascii=False),
        "validation_status": validation_status,
        "validation_errors": json.dumps(validation_errors, ensure_ascii=False),
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "model": model,
        "temperature": temperature,
        "created_at": repo.now(),
        "confirmed_at": "",
        "confirmed_by": "",
        "status": status,
        "decision_id": "",
        "edit_json": "",
        "origin_resolved": origin_resolved or "",
    })
    return did


def get_input(input_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM recorder_input WHERE id = ?", (input_id,))
    return rows[0] if rows else None


def get_draft(draft_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM recorder_draft WHERE id = ?", (draft_id,))
    return rows[0] if rows else None


def require_draft(draft_id: str, store: Store = STORE) -> Dict[str, Any]:
    row = get_draft(draft_id, store)
    if row is None:
        raise repo.ReviewError("找不到 recorder_draft：{0}".format(draft_id))
    return row


def update_draft(draft_id: str, fields: Dict[str, Any], store: Store = STORE) -> None:
    if not fields:
        return
    sets = ", ".join("{0} = ?".format(k) for k in fields)
    params = list(fields.values()) + [draft_id]
    with store.connect() as conn:
        conn.execute("UPDATE recorder_draft SET {0} WHERE id = ?".format(sets), params)


def insert_shadow(
    input_event_id: str,
    primary_draft_id: str,
    model: str,
    raw_agent_output: str,
    parsed: Dict[str, Any],
    same_fields: List[Any],
    different_fields: List[Any],
    critical_differences: List[Any],
    grounding_failures: List[Any],
    store: Store = STORE,
) -> str:
    sid = _next_id("RS", "recorder_shadow", store)
    repo._insert(store, "recorder_shadow", {
        "id": sid,
        "input_event_id": input_event_id,
        "primary_draft_id": primary_draft_id or "",
        "model": model,
        "raw_agent_output": raw_agent_output or "",
        "parsed_json": json.dumps(parsed, ensure_ascii=False),
        "same_fields": json.dumps(same_fields, ensure_ascii=False),
        "different_fields": json.dumps(different_fields, ensure_ascii=False),
        "critical_differences": json.dumps(critical_differences, ensure_ascii=False),
        "shadow_grounding_failures": json.dumps(grounding_failures, ensure_ascii=False),
        "created_at": repo.now(),
    })
    return sid


def shadows_for(input_event_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    if not input_event_id:
        return []
    return store.query(
        "SELECT * FROM recorder_shadow WHERE input_event_id = ? ORDER BY created_at",
        (input_event_id,),
    )


def open_drafts_for(code: str, store: Store = STORE) -> List[Dict[str, Any]]:
    if not code:
        return []
    return store.query(
        "SELECT id, code, name, status, thesis, origin FROM decision"
        " WHERE code = ? AND status IN ('DRAFT','PLANNED') ORDER BY opened_on DESC",
        (code,),
    )
