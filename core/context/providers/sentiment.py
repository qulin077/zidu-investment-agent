"""市场阶段。只复用已有 mkt_stage。当日 EOD 行在收盘前不可用。"""
from __future__ import annotations

from typing import Any, Dict

from core.context import io, temporal
from core.store import Store

CSV = io.repo_path("data", "raw", "movers", "emotion_daily.csv")
ROTATION = io.repo_path("data", "raw", "rotation", "latest_rotation.json")


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
        future = any(
            temporal.is_available(str(r.get("date") or "")[:10], "", cutoff_at, temporal.END_OF_DAY_SENTIMENT)
            == temporal.FUTURE
            for r in records
        )
        if future:
            payload = {
                "mkt_stage": io.dated_field(None, str(records[-1].get("date") or "")[:10],
                                            cutoff_at, "emotion_daily.csv", temporal.END_OF_DAY_SENTIMENT),
            }
            return {
                "provider": "sentiment",
                "status": "missing",
                "payload": payload,
                "coverage": "missing",
                "freshness": "future",
                "source_refs": [],
            }
        return _missing()
    freshness = io._freshness(day, cutoff_at, kind=temporal.END_OF_DAY_SENTIMENT)
    stage = str(row.get("mkt_stage") or "")
    rot_data, _rot_flag, rot_gen = io.load_latest(ROTATION, cutoff_at)
    bank = ((rot_data.get("bank_trend") or {}).get("level")) if rot_data else None
    payload = {
        "mkt_stage": io.dated_field(stage or None, day, cutoff_at, "emotion_daily.csv",
                                    temporal.END_OF_DAY_SENTIMENT),
        "mkt_stage_why": io.dated_field(
            str(row.get("mkt_stage_why") or "") or None, day, cutoff_at,
            "emotion_daily.csv", temporal.END_OF_DAY_SENTIMENT,
        ),
        "limit_up_count": io.dated_field(
            _num(row.get("limit_up_count")), day, cutoff_at,
            "emotion_daily.csv", temporal.END_OF_DAY_SENTIMENT,
        ),
        "zhaban_rate": io.dated_field(
            _num(row.get("zhaban_rate")), day, cutoff_at,
            "emotion_daily.csv", temporal.END_OF_DAY_SENTIMENT,
        ),
        "bank_b_level": io.snapshot_field(bank, rot_gen, cutoff_at, "latest_rotation.json"),
    }
    return {
        "provider": "sentiment",
        "status": "ok" if stage else "missing",
        "payload": payload,
        "coverage": "full" if stage and freshness == "fresh" else ("partial" if stage else "missing"),
        "freshness": freshness if stage else "missing",
        "source_refs": [{"field": "mkt_stage", "source": "data/raw/movers/emotion_daily.csv", "as_of": day}],
    }


def _num(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _missing() -> Dict[str, Any]:
    return {
        "provider": "sentiment",
        "status": "missing",
        "payload": {},
        "coverage": "missing",
        "freshness": "missing",
        "source_refs": [],
    }
