"""Operational Error：主流程失败可观察，且不得递归写 product_event。"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from core.config import LOG_DIR
from core.review import flags, repo
from core.store import STORE, Store

ERROR_LOG = LOG_DIR / "product_event_errors.log"


def record(
    component: str,
    operation: str,
    error_message: str,
    error_code: str = "",
    entity_type: str = "",
    entity_id: str = "",
    store: Store = STORE,
) -> Optional[str]:
    """底层落库 + 文件。禁止调用 product_event.emit。"""
    row_id = "OE-{0}".format(uuid.uuid4().hex[:12])
    occurred = repo.now()
    payload = {
        "id": row_id,
        "component": component or "unknown",
        "operation": operation or "",
        "occurred_at": occurred,
        "error_code": error_code or "",
        "error_message": (error_message or "")[:1000],
        "entity_type": entity_type or "",
        "entity_id": entity_id or "",
        "environment": flags.current_environment(),
        "resolved": 0,
    }
    try:
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO operational_error (id, component, operation, occurred_at, error_code,"
                " error_message, entity_type, entity_id, environment, resolved)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    payload["id"], payload["component"], payload["operation"],
                    payload["occurred_at"], payload["error_code"], payload["error_message"],
                    payload["entity_type"], payload["entity_id"], payload["environment"],
                    payload["resolved"],
                ),
            )
    except Exception:  # noqa: BLE001
        row_id = None
    try:
        _append_log(payload)
    except Exception:  # noqa: BLE001
        pass
    return row_id


def _append_log(payload: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = "{occurred_at} {component} {operation} {error_code} {entity_type}:{entity_id} {error_message}\n".format(
        **payload
    )
    with ERROR_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)


def list_errors(
    component: str = "",
    store: Store = STORE,
    limit: int = 200,
):
    sql = "SELECT * FROM operational_error WHERE 1=1"
    params: list[Any] = []
    if component:
        sql += " AND component = ?"
        params.append(component)
    sql += " ORDER BY occurred_at DESC LIMIT ?"
    params.append(limit)
    try:
        return store.query(sql, params)
    except Exception:  # noqa: BLE001
        return []
