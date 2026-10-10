"""ENTRY / REVIEW cutoff。宁可未知，不假设「今天收盘已经发生」。"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from core.context.temporal import has_clock, iso, parse_dt
from core.review import lifecycle, repo
from core.store import Store


def _iso_or_empty(raw: str) -> str:
    dt = parse_dt(raw)
    return iso(dt) if dt else ""


def resolve_entry_cutoff(decision: Dict[str, Any]) -> Tuple[str, str]:
    """witnessed_at → created_at → opened_on。只有带时钟的时间戳才算 known。"""
    for key in ("witnessed_at", "created_at"):
        raw = str(decision.get(key) or "").strip()
        if has_clock(raw) and parse_dt(raw):
            return _iso_or_empty(raw), "known"
    for key in ("witnessed_at", "created_at", "opened_on"):
        raw = str(decision.get(key) or "").strip()
        if parse_dt(raw):
            return _iso_or_empty(raw[:10]), "unknown"
    return "", "unknown"


def resolve_review_cutoff(
    decision_id: str,
    store: Store,
    decision: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """REVIEW_PENDING.occurred_at。不用 repo.today()。"""
    try:
        trans = repo.transitions_of(decision_id, store)
    except Exception:  # noqa: BLE001
        trans = []
    pending = [t for t in trans if t.get("to_status") == lifecycle.REVIEW_PENDING]
    if pending:
        raw = str(pending[-1].get("occurred_at") or "").strip()
        dt = parse_dt(raw)
        if dt is not None:
            return iso(dt), "known" if has_clock(raw) else "unknown"
    row = decision or {}
    fallback, _ = resolve_entry_cutoff(row)
    return fallback, "unknown"


def resolve_cutoff(
    decision: Dict[str, Any],
    snapshot_type: str,
    store: Store,
    existing: Optional[Dict[str, Any]] = None,
    retry: bool = False,
    override: str = "",
) -> Tuple[str, str]:
    if override and parse_dt(override):
        raw = override.strip()
        return _iso_or_empty(raw), "known" if has_clock(raw) else "unknown"
    if retry and existing and parse_dt(str(existing.get("cutoff_at") or "")):
        raw = str(existing.get("cutoff_at") or "")
        conf = existing.get("temporal_confidence") or ("known" if has_clock(raw) else "unknown")
        return _iso_or_empty(raw), conf
    if snapshot_type == "REVIEW_CONTEXT":
        return resolve_review_cutoff(decision.get("id") or "", store, decision)
    return resolve_entry_cutoff(decision)
