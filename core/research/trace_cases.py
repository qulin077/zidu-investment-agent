"""Research trace snapshots for diagnosis, regression and product storytelling.

Runtime snapshots stay local under ``data/diagnostics``.  They contain only
public action traces and bounded user-visible messages; hidden model reasoning,
credentials and source bodies are deliberately excluded.  A human can later
promote a useful snapshot into ``evals/research/bad_cases``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from core.research import sessions
from core.research.store import now_iso


_HIDDEN_KEYS = {
    "chain_of_thought", "thinking", "reasoning", "hidden", "raw_output",
    "api_key", "authorization", "cookie", "token", "secret", "password",
}
_TOKEN = re.compile(
    r"(?i)(bearer\s+)?[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]{10,}){1,4}"
)


def capture_candidate(store, session_id: str, run_id: str, *, status: str, completion: dict | None = None) -> dict:
    """Persist a private candidate only when the run is diagnostically useful."""
    completion = dict(completion or {})
    events = [row for row in sessions.list_events(store, session_id) if row.get("run_id") == run_id]
    if not _notable(status, completion, events):
        return {}
    payload = build_snapshot(store, session_id, [run_id])
    payload["candidate_reason"] = _candidate_reason(status, completion, events)
    payload["completion"] = _clean(completion)
    root = Path(store.path).parent / "diagnostics" / "research_cases"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "{0}-{1}.json".format(session_id, run_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), "reason": payload["candidate_reason"]}


def build_snapshot(store, session_id: str, run_ids: list[str] | None = None) -> dict:
    bundle = sessions.bundle(store, session_id) or {}
    selected = set(run_ids or [])
    messages = []
    for row in bundle.get("messages") or []:
        if selected and row.get("run_id") not in selected:
            continue
        messages.append({
            "run_id": row.get("run_id") or "",
            "role": row.get("role") or "",
            "content": _clean_text(row.get("content") or "", 4000),
            "created_at": row.get("created_at") or "",
        })
    events = []
    for row in bundle.get("events") or []:
        if selected and row.get("run_id") not in selected:
            continue
        events.append({
            "seq": row.get("seq"), "run_id": row.get("run_id") or "",
            "event_type": row.get("event_type") or "", "status": row.get("status") or "",
            "payload": _clean(row.get("payload") or {}), "created_at": row.get("created_at") or "",
        })
    runs = []
    for row in bundle.get("runs") or []:
        if selected and row.get("id") not in selected:
            continue
        runs.append({
            "id": row.get("id") or "", "skill": row.get("skill") or "",
            "status": row.get("status") or "", "mode": row.get("mode") or "",
            "question": _clean_text(row.get("question") or "", 1000),
            "tool_calls": row.get("tool_calls") or 0, "llm_calls": row.get("llm_calls") or 0,
            "error_code": row.get("error_code") or "", "error_message": _clean_text(row.get("error_message") or "", 500),
            "started_at": row.get("started_at") or "", "finished_at": row.get("finished_at") or "",
        })
    session = bundle.get("session") or {}
    return {
        "schema_version": "research-bad-case/v1",
        "captured_at": now_iso(),
        "privacy": "LOCAL_PRIVATE_REDACTED",
        "trace_policy": "PUBLIC_ACTIONS_ONLY_NO_HIDDEN_REASONING",
        "session": {
            "id": session.get("id") or session_id,
            "title": _clean_text(session.get("title") or "", 160),
            "skill": session.get("skill") or "", "status": session.get("status") or "",
            "primary_entity_type": session.get("primary_entity_type") or "",
            "primary_entity_name": session.get("primary_entity_name") or "",
            "primary_entity_code": session.get("primary_entity_code") or "",
        },
        "runs": runs, "messages": messages, "events": events,
    }


def _notable(status: str, completion: dict, events: list[dict]) -> bool:
    if status in {"UNAVAILABLE", "INTERRUPTED", "CLARIFY"}:
        return True
    if completion.get("status") in {"PARTIAL", "SOURCE_UNAVAILABLE"}:
        return True
    return any(row.get("status") in {"failed", "gap"} for row in events)


def _candidate_reason(status: str, completion: dict, events: list[dict]) -> list[str]:
    reasons = []
    if status in {"UNAVAILABLE", "INTERRUPTED", "CLARIFY"}:
        reasons.append(status)
    if completion.get("status") in {"PARTIAL", "SOURCE_UNAVAILABLE"}:
        reasons.append("COVERAGE_{0}".format(completion.get("status")))
    failed_types = sorted({row.get("event_type") for row in events if row.get("status") in {"failed", "gap"}})
    reasons.extend("TRACE_{0}".format(item.upper()) for item in failed_types if item)
    return reasons


def _clean(value):
    if isinstance(value, dict):
        return {
            key: _clean(item)
            for key, item in value.items()
            if key.lower() not in _HIDDEN_KEYS and not any(secret in key.lower() for secret in ("password", "secret", "token", "authorization", "cookie"))
        }
    if isinstance(value, list):
        return [_clean(item) for item in value[:100]]
    if isinstance(value, str):
        return _clean_text(value, 4000)
    return value


def _clean_text(value: str, limit: int) -> str:
    redacted = _TOKEN.sub("[REDACTED_TOKEN]", value or "")
    return redacted[:limit]
