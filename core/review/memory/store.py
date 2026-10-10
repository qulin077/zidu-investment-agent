"""Mistake / Pattern / Rule 存取。Web 不直接写 SQL。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.review import repo
from core.store import STORE, Store


def _next_id(prefix: str, table: str, store: Store) -> str:
    day = repo.today().replace("-", "")
    head = "{0}-{1}-".format(prefix, day)
    return "{0}{1:04d}".format(head, repo._next_seq(store, table, head))


def insert(table: str, row: Dict[str, Any], store: Store = STORE) -> None:
    repo._insert(store, table, row)


def update(table: str, row_id: str, fields: Dict[str, Any], store: Store = STORE) -> None:
    if not fields:
        return
    sets = ", ".join("{0} = ?".format(k) for k in fields)
    sql = "UPDATE {0} SET {1} WHERE id = ?".format(table, sets)
    with store.connect() as conn:
        conn.execute(sql, tuple(fields[k] for k in fields) + (row_id,))


def get_mistake(mistake_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM mistake_instance WHERE id = ?", (mistake_id,))
    return rows[0] if rows else None


def mistake_for_decision(decision_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM mistake_instance WHERE decision_id = ?", (decision_id,))
    return rows[0] if rows else None


def list_mistakes(store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query("SELECT * FROM mistake_instance ORDER BY created_at, id")


def get_pattern(pattern_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM pattern WHERE id = ?", (pattern_id,))
    return rows[0] if rows else None


def pattern_by_key(pattern_key: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM pattern WHERE pattern_key = ?", (pattern_key,))
    return rows[0] if rows else None


def list_patterns(store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query("SELECT * FROM pattern ORDER BY last_seen_at DESC, created_at DESC")


def evidence_of(pattern_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM pattern_evidence WHERE pattern_id = ? ORDER BY added_at, decision_id",
        (pattern_id,),
    )


def add_evidence(pattern_id: str, mistake_id: str, decision_id: str, store: Store = STORE) -> None:
    existing = store.query(
        "SELECT 1 FROM pattern_evidence WHERE pattern_id = ? AND mistake_id = ?",
        (pattern_id, mistake_id),
    )
    if existing:
        return
    insert("pattern_evidence", {
        "pattern_id": pattern_id,
        "mistake_id": mistake_id,
        "decision_id": decision_id,
        "added_at": repo.now(),
    }, store)


def move_evidence(from_id: str, to_id: str, store: Store = STORE) -> int:
    rows = evidence_of(from_id, store)
    moved = 0
    with store.connect() as conn:
        for row in rows:
            already = conn.execute(
                "SELECT 1 FROM pattern_evidence WHERE pattern_id = ? AND mistake_id = ?",
                (to_id, row["mistake_id"]),
            ).fetchone()
            if already:
                conn.execute(
                    "DELETE FROM pattern_evidence WHERE pattern_id = ? AND mistake_id = ?",
                    (from_id, row["mistake_id"]),
                )
                continue
            conn.execute(
                "UPDATE pattern_evidence SET pattern_id = ? WHERE pattern_id = ? AND mistake_id = ?",
                (to_id, from_id, row["mistake_id"]),
            )
            moved += 1
    return moved + len(rows)


def get_rule(rule_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM rule WHERE id = ?", (rule_id,))
    return rows[0] if rows else None


def rules_for_pattern(pattern_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM rule WHERE pattern_id = ? ORDER BY created_at",
        (pattern_id,),
    )


def list_rules(status: str = "", store: Store = STORE) -> List[Dict[str, Any]]:
    if status:
        return store.query("SELECT * FROM rule WHERE status = ? ORDER BY created_at DESC", (status,))
    return store.query("SELECT * FROM rule ORDER BY created_at DESC")


def active_rules(store: Store = STORE) -> List[Dict[str, Any]]:
    return list_rules("ACTIVE", store)


def revisions_of(rule_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM rule_revision WHERE rule_id = ? ORDER BY changed_at",
        (rule_id,),
    )


def violations_of(rule_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM rule_violation WHERE rule_id = ? ORDER BY detected_at",
        (rule_id,),
    )


def violation_for(rule_id: str, decision_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query(
        "SELECT * FROM rule_violation WHERE rule_id = ? AND decision_id = ?",
        (rule_id, decision_id),
    )
    return rows[0] if rows else None


def reminders_for(decision_id: str, store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query(
        "SELECT * FROM memory_reminder WHERE decision_id = ? ORDER BY created_at",
        (decision_id,),
    )


def get_reminder(reminder_id: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query("SELECT * FROM memory_reminder WHERE id = ?", (reminder_id,))
    return rows[0] if rows else None


def list_reminders(store: Store = STORE) -> List[Dict[str, Any]]:
    return store.query("SELECT * FROM memory_reminder ORDER BY created_at")


def next_rule_id(store: Store) -> str:
    return _next_id("RU", "rule", store)


def next_revision_id(store: Store) -> str:
    return _next_id("RR", "rule_revision", store)


def next_violation_id(store: Store) -> str:
    return _next_id("RVIO", "rule_violation", store)


def next_reminder_id(store: Store) -> str:
    return _next_id("RM", "memory_reminder", store)


def next_fact_id(store: Store) -> str:
    return _next_id("DF", "decision_pattern_fact", store)


def parse_json(raw: Any, default: Any):
    if isinstance(raw, (list, dict)):
        return raw
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default
