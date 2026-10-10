"""guided_review_session / turn / attribution_draft。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.review import repo
from core.store import STORE, Store


def _next(prefix: str, table: str, store: Store) -> str:
    day = repo.today().replace("-", "")
    head = "{0}-{1}-".format(prefix, day)
    return "{0}{1:04d}".format(head, repo._next_seq(store, table, head))


def insert_session(
    decision_id: str,
    prompt_version: str,
    model: str,
    context_hash: str,
    store: Store = STORE,
) -> str:
    sid = _next("GS", "guided_review_session", store)
    repo._insert(store, "guided_review_session", {
        "id": sid,
        "decision_id": decision_id,
        "status": "OPEN",
        "prompt_version": prompt_version,
        "model": model,
        "context_hash": context_hash,
        "created_at": repo.now(),
        "confirmed_at": "",
        "review_id": "",
    })
    return sid


def get_session(session_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM guided_review_session WHERE id = ?", (session_id,))
    return rows[0] if rows else None


def open_session_for(decision_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query(
        "SELECT * FROM guided_review_session WHERE decision_id = ?"
        " AND status IN ('OPEN','WAITING_USER','DRAFT') ORDER BY created_at DESC",
        (decision_id,),
    )
    return rows[0] if rows else None


def update_session(session_id: str, fields: Dict[str, Any], store: Store = STORE) -> None:
    if not fields:
        return
    sets = ", ".join("{0} = ?".format(k) for k in fields)
    params = list(fields.values()) + [session_id]
    with store.connect() as conn:
        conn.execute("UPDATE guided_review_session SET {0} WHERE id = ?".format(sets), params)


def insert_turn(
    session_id: str,
    turn_index: int,
    unresolved: str,
    question: str,
    raw_agent_output: str,
    parsed: Dict[str, Any],
    store: Store = STORE,
) -> str:
    tid = _next("GT", "guided_review_turn", store)
    repo._insert(store, "guided_review_turn", {
        "id": tid,
        "session_id": session_id,
        "turn_index": turn_index,
        "unresolved": unresolved,
        "question": question,
        "raw_agent_output": raw_agent_output,
        "parsed_json": json.dumps(parsed, ensure_ascii=False),
        "user_answer": "",
        "created_at": repo.now(),
        "answered_at": "",
    })
    return tid


def turns_of(session_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM guided_review_turn WHERE session_id = ? ORDER BY turn_index, id",
        (session_id,),
    )


def update_turn(turn_id: str, fields: Dict[str, Any], store: Store = STORE) -> None:
    sets = ", ".join("{0} = ?".format(k) for k in fields)
    params = list(fields.values()) + [turn_id]
    with store.connect() as conn:
        conn.execute("UPDATE guided_review_turn SET {0} WHERE id = ?".format(sets), params)


def insert_attr_draft(
    session_id: str,
    decision_id: str,
    parsed: Dict[str, Any],
    primary_error: str = "",
    evidence: Optional[List[Any]] = None,
    store: Store = STORE,
) -> str:
    aid = _next("AD", "attribution_draft", store)
    repo._insert(store, "attribution_draft", {
        "id": aid,
        "session_id": session_id,
        "decision_id": decision_id,
        "parsed_json": json.dumps(parsed, ensure_ascii=False),
        "primary_error": primary_error or "",
        "evidence": json.dumps(list(evidence or []), ensure_ascii=False),
        "user_confirmed": 0,
        "confirmed_at": "",
        "created_at": repo.now(),
    })
    return aid


def latest_attr_draft(decision_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query(
        "SELECT * FROM attribution_draft WHERE decision_id = ? ORDER BY created_at DESC, id DESC",
        (decision_id,),
    )
    return rows[0] if rows else None


def update_attr_draft(draft_id: str, fields: Dict[str, Any], store: Store = STORE) -> None:
    sets = ", ".join("{0} = ?".format(k) for k in fields)
    params = list(fields.values()) + [draft_id]
    with store.connect() as conn:
        conn.execute("UPDATE attribution_draft SET {0} WHERE id = ?".format(sets), params)
