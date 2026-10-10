"""origin 只能由关联的第一笔 Execution 相对 witnessed_at 结算。

允许 EX_ANTE → POST_HOC。禁止 POST_HOC → EX_ANTE。
成交只有日期、没有时刻时，没有事前证据，降 POST_HOC。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.review import repo
from core.store import STORE, Store

PROVISIONAL = "PROVISIONAL"
SETTLED = "SETTLED"
KNOWN = "KNOWN"
UNKNOWN = "UNKNOWN"


class OriginError(repo.ReviewError):
    pass


def _stamp(raw: str) -> str:
    return (raw or "").replace(" ", "T")[:19]


def _has_clock(executed_at: str) -> bool:
    text = (executed_at or "").strip()
    if not text or text in ("00:00:00", "00:00"):
        return False
    return True


def create_origin(mode: str) -> Dict[str, str]:
    if (mode or "").lower() in ("posthoc", "post_hoc", "retrospective"):
        return {"origin": "POST_HOC", "origin_status": SETTLED, "origin_confidence": KNOWN}
    return {"origin": "EX_ANTE", "origin_status": PROVISIONAL, "origin_confidence": KNOWN}


def execution_stamp(ex: Dict[str, Any]) -> Optional[str]:
    day = (ex.get("executed_on") or "")[:10]
    clock = (ex.get("executed_at") or "").strip()
    if not day:
        return None
    if not _has_clock(clock):
        return None
    if len(clock) == 5:
        clock = clock + ":00"
    return "{0}T{1}".format(day, clock)[:19]


def maybe_settle_on_attach(
    decision_id: str,
    execution: Dict[str, Any],
    changed_by: str = "system",
    store: Store = STORE,
) -> Dict[str, Any]:
    """首笔关联成交时结算 origin。已 POST_HOC 的不再动。"""
    row = repo.require_decision(decision_id, store)
    origin = (row.get("origin") or "EX_ANTE").upper()
    if origin == "POST_HOC":
        return {"changed": False, "origin": "POST_HOC", "reason": "already POST_HOC"}
    linked = repo.executions(decision_id, store)
    # attach 之后当前这笔已在列表里
    if len(linked) > 1:
        return {"changed": False, "origin": origin, "reason": "not first linked execution"}

    witnessed = _stamp(row.get("witnessed_at") or "")
    if not witnessed:
        _set_status(decision_id, SETTLED, KNOWN, store)
        return {"changed": False, "origin": origin, "reason": "no witnessed_at to compare"}
    stamp = execution_stamp(execution)
    if stamp is None:
        return degrade_to_post_hoc(
            decision_id,
            "成交没有精确时间，不能证明事前",
            changed_by,
            confidence=UNKNOWN,
            store=store,
        )
    if witnessed and stamp < witnessed:
        return degrade_to_post_hoc(
            decision_id,
            "first_linked_execution {0} 早于 witnessed_at {1}".format(stamp, witnessed),
            changed_by,
            store=store,
        )
    _set_status(decision_id, SETTLED, KNOWN, store)
    return {"changed": False, "origin": "EX_ANTE", "origin_status": SETTLED}


def degrade_to_post_hoc(
    decision_id: str,
    reason: str,
    changed_by: str = "system",
    confidence: str = KNOWN,
    store: Store = STORE,
) -> Dict[str, Any]:
    row = repo.require_decision(decision_id, store)
    origin = (row.get("origin") or "EX_ANTE").upper()
    if origin == "POST_HOC":
        return {"changed": False, "origin": "POST_HOC"}
    if origin != "EX_ANTE":
        raise OriginError("未知 origin：{0}".format(origin))
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO revision (table_name, row_id, field, old_value, new_value,"
            " reason, changed_at, changed_by, source) VALUES (?,?,?,?,?,?,?,?,?)",
            ("decision", decision_id, "origin", "EX_ANTE", "POST_HOC",
             reason, repo.now(), changed_by, "system"),
        )
        conn.execute(
            "UPDATE decision SET origin = 'POST_HOC', origin_status = ?, origin_confidence = ?,"
            " revision = revision + 1 WHERE id = ?",
            (SETTLED, confidence, decision_id),
        )
    return {
        "changed": True, "origin": "POST_HOC", "from": "EX_ANTE",
        "reason": reason, "origin_confidence": confidence,
    }


def assert_not_upgrade(old: str, new: str) -> None:
    if (old or "").upper() == "POST_HOC" and (new or "").upper() == "EX_ANTE":
        raise OriginError("origin 只能单向降级：POST_HOC 不能升回 EX_ANTE")


def _set_status(decision_id: str, status: str, confidence: str, store: Store) -> None:
    with store.connect() as conn:
        conn.execute(
            "UPDATE decision SET origin_status = ?, origin_confidence = ? WHERE id = ?",
            (status, confidence, decision_id),
        )
