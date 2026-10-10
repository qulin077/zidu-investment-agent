"""产品行为日志。只记发生了什么，不记模型 Chain-of-Thought，不存整份 Decision。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from core.review import flags, repo
from core.store import STORE, Store

KEY_TYPES = {
    "RECORDER_INPUT_RECEIVED",
    "RECORDER_DRAFT_CONFIRMED",
    "RECORDER_DRAFT_REJECTED",
    "REVIEW_COMPLETED",
    "PATTERN_CONFIRMED",
    "PATTERN_DISMISSED",
    "RULE_ACTIVATED",
    "RULE_REJECTED",
    "RULE_RETIRED",
}


def emit(
    event_type: str,
    entity_type: str = "",
    entity_id: str = "",
    source: str = "system",
    metadata: Optional[Dict[str, Any]] = None,
    store: Store = STORE,
) -> Optional[str]:
    meta = dict(metadata or {})
    if flags.pilot_mode() and "trade_date" not in meta:
        meta["trade_date"] = repo.today()
    payload = {
        "id": "PE-{0}".format(uuid.uuid4().hex[:12]),
        "event_type": event_type,
        "occurred_at": repo.now(),
        "entity_type": entity_type or "",
        "entity_id": entity_id or "",
        "source": source,
        "metadata_json": json.dumps(meta, ensure_ascii=False, sort_keys=True),
        "environment": flags.current_environment(),
        "demo": 1 if flags.is_demo() else 0,
    }
    try:
        with store.connect() as conn:
            if event_type in KEY_TYPES and entity_id:
                exists = conn.execute(
                    "SELECT id FROM product_event WHERE event_type = ? AND entity_type = ? AND entity_id = ?",
                    (event_type, entity_type or "", entity_id),
                ).fetchone()
                if exists:
                    return exists[0]
            conn.execute(
                "INSERT INTO product_event (id, event_type, occurred_at, entity_type, entity_id,"
                " source, metadata_json, environment, demo) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    payload["id"], payload["event_type"], payload["occurred_at"],
                    payload["entity_type"], payload["entity_id"], payload["source"],
                    payload["metadata_json"], payload["environment"], payload["demo"],
                ),
            )
        return payload["id"]
    except Exception as exc:  # noqa: BLE001 — 产品日志不得阻断主流程
        try:
            from core.ops.errors import record as record_operr
            record_operr(
                "product_event",
                "insert",
                str(exc),
                error_code="EVENT_INSERT_FAILED",
                entity_type=entity_type,
                entity_id=entity_id,
                store=store,
            )
        except Exception:  # noqa: BLE001
            pass
        return None


def list_events(
    event_type: str = "",
    entity_id: str = "",
    include_demo: bool = False,
    store: Store = STORE,
):
    sql = "SELECT * FROM product_event WHERE 1=1"
    params: list = []
    if event_type:
        sql += " AND event_type = ?"
        params.append(event_type)
    if entity_id:
        sql += " AND entity_id = ?"
        params.append(entity_id)
    if not include_demo:
        sql += " AND demo = 0 AND environment NOT IN ('test','eval','demo')"
    sql += " ORDER BY occurred_at, id"
    try:
        return store.query(sql, params)
    except Exception:  # noqa: BLE001
        return []
