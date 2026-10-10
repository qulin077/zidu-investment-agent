"""pipeline_run：Recorder / Intake / Guided / Context / Memory 的可观察运行记录。"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Iterable, Optional

from core.review import repo
from core.store import STORE, Store


def start(
    pipeline: str,
    entity_ids: Optional[Iterable[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    store: Store = STORE,
) -> str:
    run_id = "PR-{0}".format(uuid.uuid4().hex[:12])
    try:
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO pipeline_run (id, pipeline, status, started_at, entity_ids_json, metadata_json)"
                " VALUES (?,?,?,?,?,?)",
                (
                    run_id, pipeline, "running", repo.now(),
                    json.dumps(list(entity_ids or []), ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
    except Exception:  # noqa: BLE001
        return run_id
    return run_id


def finish(
    run_id: str,
    status: str = "ok",
    error_code: str = "",
    error_message: str = "",
    entity_ids: Optional[Iterable[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    store: Store = STORE,
) -> None:
    fields = {
        "status": status,
        "finished_at": repo.now(),
        "error_code": error_code or "",
        "error_message": (error_message or "")[:500],
    }
    if entity_ids is not None:
        fields["entity_ids_json"] = json.dumps(list(entity_ids), ensure_ascii=False)
    if metadata is not None:
        fields["metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    sets = ", ".join("{0} = ?".format(k) for k in fields)
    try:
        with store.connect() as conn:
            conn.execute(
                "UPDATE pipeline_run SET {0} WHERE id = ?".format(sets),
                tuple(fields.values()) + (run_id,),
            )
    except Exception:  # noqa: BLE001
        return


def latest(pipeline: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    try:
        rows = store.query(
            "SELECT * FROM pipeline_run WHERE pipeline = ? ORDER BY started_at DESC LIMIT 1",
            (pipeline,),
        )
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        return None
