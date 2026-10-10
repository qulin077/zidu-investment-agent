"""遍历 Context payload 里的 provenance 字段。"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Tuple

from core.context import temporal


def is_field(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    return "source" in obj and ("freshness" in obj or "temporal_state" in obj)


def iter_fields(obj: Any, path: str = "") -> Iterator[Tuple[str, Dict[str, Any]]]:
    if is_field(obj):
        yield path or "field", obj
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = "{0}.{1}".format(path, key) if path else str(key)
            yield from iter_fields(value, child)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from iter_fields(value, "{0}[{1}]".format(path, i))


def stamp_captured(obj: Any, captured_at: str) -> None:
    for _, field in iter_fields(obj):
        if not field.get("captured_at"):
            field["captured_at"] = captured_at


def count_future(obj: Any) -> int:
    return sum(1 for _, field in iter_fields(obj) if _state(field) == "future")


def _state(field: Dict[str, Any]) -> str:
    return str(field.get("temporal_state") or field.get("freshness") or "")


def included(field: Dict[str, Any]) -> bool:
    if field.get("value") is None:
        return False
    return _state(field) not in ("future", "unknown")


def debug_rows(payload: Dict[str, Any], cutoff_at: str = "") -> List[Dict[str, Any]]:
    cutoff = cutoff_at or str(payload.get("cutoff_at") or "")
    rows = []
    for path, field in iter_fields(payload):
        avail = str(field.get("available_at") or "")
        flag = ""
        if avail and cutoff:
            flag = temporal.is_available(avail[:10], avail, cutoff, temporal.LATEST_SNAPSHOT)
        elif not avail:
            flag = temporal.UNKNOWN
        used = included(field)
        reason = "included"
        if _state(field) == "future":
            reason = "future: available_at > cutoff"
        elif _state(field) == "unknown":
            reason = "unknown availability"
        elif _state(field) == "missing":
            reason = "missing"
        elif used and avail and cutoff:
            cdt, adt = temporal.parse_dt(cutoff), temporal.parse_dt(avail)
            if cdt and adt and adt > cdt:
                reason = "LEAK available_at > cutoff"
        rows.append({
            "field": path,
            "source": field.get("source") or "",
            "event_time": field.get("event_time") or "",
            "available_at": avail,
            "cutoff_at": cutoff,
            "temporal_state": _state(field),
            "included": used,
            "reason": reason,
            "value": field.get("value"),
            "as_of": field.get("as_of") or "",
            "freshness": field.get("freshness") or "",
        })
    return rows


def leak_rows(payload: Dict[str, Any], cutoff_at: str) -> List[Dict[str, Any]]:
    leaks = []
    cutoff = temporal.parse_dt(cutoff_at)
    for row in debug_rows(payload, cutoff_at):
        if not row["included"]:
            continue
        avail = temporal.parse_dt(row.get("available_at") or "")
        if cutoff is None or avail is None:
            continue
        if avail > cutoff:
            leaks.append(row)
    return leaks


def unknown_included(payload: Dict[str, Any], cutoff_at: str = "") -> List[Dict[str, Any]]:
    return [
        row for row in debug_rows(payload, cutoff_at)
        if row["included"] and (
            row["temporal_state"] == "unknown"
            or (row["temporal_state"] == "available" and not row["available_at"])
        )
    ]
