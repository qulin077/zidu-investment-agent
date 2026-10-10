"""资金流。latest_rhythm 必须 generated_at <= cutoff。缺时间戳不猜。"""
from __future__ import annotations

from typing import Any, Dict

from core.context import io, temporal
from core.store import Store

RHYTHM = io.repo_path("data", "raw", "rhythm", "latest_rhythm.json")


def collect(cutoff_at: str, store: Store, decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data, flag, generated = io.load_latest(RHYTHM, cutoff_at)
    if flag != temporal.AVAILABLE:
        payload = {
            "sse_margin_yi": io.snapshot_field(None, generated, cutoff_at, "latest_rhythm.json"),
            "sse_margin_chg_5d": io.snapshot_field(None, generated, cutoff_at, "latest_rhythm.json"),
        }
        freshness = payload["sse_margin_yi"]["freshness"]
        return {
            "provider": "flow",
            "status": "missing",
            "payload": payload,
            "coverage": "missing",
            "freshness": freshness,
            "source_refs": [{"field": "sse_margin", "source": "data/raw/rhythm/latest_rhythm.json", "as_of": ""}],
        }
    margin = (data.get("margin_sse") or {}) if data else {}
    day = str(margin.get("date") or "")[:10]
    if not day:
        return {
            "provider": "flow",
            "status": "missing",
            "payload": {},
            "coverage": "missing",
            "freshness": "missing",
            "source_refs": [],
        }
    payload = {
        "sse_margin_yi": io.snapshot_field(margin.get("rz_yi"), generated, cutoff_at, "latest_rhythm.json"),
        "sse_margin_chg_5d": io.snapshot_field(
            margin.get("rz_chg_5d_yi"), generated, cutoff_at, "latest_rhythm.json",
        ),
    }
    freshness = payload["sse_margin_yi"]["freshness"]
    return {
        "provider": "flow",
        "status": "ok",
        "payload": payload,
        "coverage": "partial",
        "freshness": freshness,
        "source_refs": [{"field": "sse_margin", "source": "data/raw/rhythm/latest_rhythm.json", "as_of": day}],
    }
