"""情绪宽度事实。没有可靠数据就 abstain。EOD 行按 15:30 可见。"""
from __future__ import annotations

from typing import Any, Dict

from core.context import io, temporal
from core.store import Store

CSV = io.repo_path("data", "raw", "movers", "emotion_daily.csv")


def collect(cutoff_at: str, store: Store, decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    try:
        import pandas as pd
    except ImportError:
        return _missing()
    if not CSV.exists():
        return _missing()
    df = pd.read_csv(CSV)
    if df.empty or "date" not in df.columns:
        return _missing()
    records = df.to_dict("records")
    for rec in records:
        rec["date"] = str(rec.get("date") or "")[:10]
    row, day = io.last_available_row(records, cutoff_at, temporal.END_OF_DAY_SENTIMENT)
    if row is None:
        return _missing()
    freshness = io._freshness(day, cutoff_at, kind=temporal.END_OF_DAY_SENTIMENT)
    payload = {
        "limit_up": io.dated_field(
            _num(row.get("limit_up_count")), day, cutoff_at, "emotion_daily.csv",
            temporal.END_OF_DAY_SENTIMENT,
        ),
        "limit_down": io.dated_field(None, day, cutoff_at, "emotion_daily.csv", temporal.END_OF_DAY_SENTIMENT),
        "zhaban_rate": io.dated_field(
            _num(row.get("zhaban_rate")), day, cutoff_at, "emotion_daily.csv",
            temporal.END_OF_DAY_SENTIMENT,
        ),
        "seal_rate": io.dated_field(
            _num(row.get("seal_rate")), day, cutoff_at, "emotion_daily.csv",
            temporal.END_OF_DAY_SENTIMENT,
        ),
        "advancers": io.dated_field(None, "", cutoff_at, "emotion_daily.csv", temporal.END_OF_DAY_SENTIMENT),
        "decliners": io.dated_field(None, "", cutoff_at, "emotion_daily.csv", temporal.END_OF_DAY_SENTIMENT),
    }
    # limit_down / advancers 无列：标 missing，不要假装 available
    payload["limit_down"]["freshness"] = "missing"
    payload["limit_down"]["temporal_state"] = "missing"
    payload["limit_down"]["value"] = None
    payload["advancers"]["freshness"] = "missing"
    payload["advancers"]["temporal_state"] = "missing"
    payload["decliners"]["freshness"] = "missing"
    payload["decliners"]["temporal_state"] = "missing"
    return {
        "provider": "breadth",
        "status": "ok",
        "payload": payload,
        "coverage": "partial",
        "freshness": freshness,
        "source_refs": [{"field": "breadth", "source": "data/raw/movers/emotion_daily.csv", "as_of": day}],
    }


def _num(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _missing() -> Dict[str, Any]:
    return {
        "provider": "breadth",
        "status": "missing",
        "payload": {},
        "coverage": "missing",
        "freshness": "missing",
        "source_refs": [],
    }
