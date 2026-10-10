"""Decision Context 契约。事实快照，不是交易建议。"""
from __future__ import annotations

from core.context.temporal import TEMPORAL_POLICY_VERSION  # noqa: F401

CONTEXT_VERSION = "c1"
ENTRY_CONTEXT = "ENTRY_CONTEXT"
REVIEW_CONTEXT = "REVIEW_CONTEXT"
SNAPSHOT_TYPES = (ENTRY_CONTEXT, REVIEW_CONTEXT)
STALE_DAYS = 3
KEY_PROVIDERS = ("market", "sentiment", "overseas")


def provenance(
    value,
    as_of: str,
    source: str,
    freshness: str,
    event_time: str = "",
    available_at: str = "",
    captured_at: str = "",
    temporal_state: str = "",
    source_as_of: str = "",
) -> dict:
    state = temporal_state or (
        "future" if freshness == "future"
        else "unknown" if freshness == "unknown"
        else "missing" if freshness == "missing"
        else "available"
    )
    usable = value
    if state in ("future", "unknown") or freshness == "future":
        usable = None
    return {
        "value": usable,
        "as_of": as_of or "",
        "event_time": event_time or "",
        "available_at": available_at or "",
        "captured_at": captured_at or "",
        "source": source,
        "freshness": freshness,
        "temporal_state": state,
        "source_as_of": source_as_of or as_of or "",
    }
