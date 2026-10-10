from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import ROOT
from core.context import temporal
from core.context.schema import provenance
from core.store import Store


def _freshness(as_of: str, snapshot_as_of: str, stale_days: int = temporal.STALE_DAYS,
               kind: str = temporal.DAILY_CLOSE) -> str:
    """as_of=数据日，snapshot_as_of=cutoff。未来数据是 future，不再标 fresh。"""
    if not as_of:
        return "missing"
    avail = temporal.available_at(as_of, "", kind)
    return temporal.freshness(temporal.iso(avail) if avail else "", snapshot_as_of, stale_days)


@lru_cache(maxsize=64)
def _csv_closes_cached(path: str, mtime: int) -> tuple:
    import pandas as pd
    df = pd.read_csv(path)
    if df.empty:
        return tuple()
    date_col = "日期" if "日期" in df.columns else ("date" if "date" in df.columns else "")
    close_col = "收盘" if "收盘" in df.columns else ("close" if "close" in df.columns else "")
    if not date_col or not close_col:
        return tuple()
    df = df.copy()
    df[date_col] = df[date_col].astype(str)
    df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
    df = df.dropna(subset=[close_col]).sort_values(date_col)
    return tuple((str(d)[:10], float(c)) for d, c in zip(df[date_col], df[close_col]))


def read_csv_closes(path: Path) -> List[Tuple[str, float]]:
    if not path.exists():
        return []
    try:
        return list(_csv_closes_cached(str(path), int(path.stat().st_mtime)))
    except Exception:  # noqa: BLE001
        return []


def store_closes(store: Store, code: str) -> List[Tuple[str, float]]:
    rows = store.query(
        "SELECT date, close FROM quote_daily WHERE code = ? AND close IS NOT NULL ORDER BY date",
        (code,),
    )
    return [(str(r["date"])[:10], float(r["close"])) for r in rows if r.get("close") is not None]


def window_returns(
    series: List[Tuple[str, float]],
    cutoff_at: str,
    windows=(1, 5, 20),
    kind: str = temporal.DAILY_CLOSE,
) -> Dict[str, Any]:
    clipped = []
    for day, close in series:
        if temporal.is_available(day, "", cutoff_at, kind) == temporal.AVAILABLE:
            clipped.append((day, close))
    if not clipped:
        return {}
    last_d, last_c = clipped[-1]
    out: Dict[str, Any] = {"as_of": last_d, "close": last_c}
    for n in windows:
        if len(clipped) <= n:
            out["ret_{0}d".format(n)] = None
            continue
        prev = clipped[-1 - n][1]
        out["ret_{0}d".format(n)] = None if not prev else round((last_c / prev - 1) * 100, 4)
    return out


def field_from_series(
    series: List[Tuple[str, float]],
    cutoff_at: str,
    source: str,
    key: str,
    n: int,
    kind: str = temporal.DAILY_CLOSE,
) -> Dict[str, Any]:
    stats = window_returns(series, cutoff_at, kind=kind)
    if not stats:
        future = any(
            temporal.is_available(d, "", cutoff_at, kind) == temporal.FUTURE for d, _ in series
        )
        state = "future" if future else "missing"
        return provenance(
            None, "", source, state, temporal_state=state,
        )
    day = stats.get("as_of") or ""
    avail = temporal.available_at(day, "", kind)
    avail_s = temporal.iso(avail) if avail else ""
    fresh = temporal.freshness(avail_s, cutoff_at)
    return provenance(
        stats.get("ret_{0}d".format(n)),
        day,
        source,
        fresh,
        event_time=temporal.event_time_for(day, kind),
        available_at=avail_s,
        temporal_state=temporal.temporal_state_for(temporal.AVAILABLE, fresh),
    )


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_latest(path: Path, cutoff_at: str) -> Tuple[Optional[Dict[str, Any]], str, str]:
    """返回 (payload_or_none, availability, generated_at). 缺时钟 → UNKNOWN，不猜。"""
    data = load_json(path)
    if not data:
        return None, temporal.UNKNOWN, ""
    generated = str(data.get("generated_at") or data.get("asof") or "")
    if not generated:
        return None, temporal.UNKNOWN, ""
    if not temporal.has_clock(generated):
        return None, temporal.UNKNOWN, generated
    flag = temporal.is_available(generated[:10], generated, cutoff_at, temporal.LATEST_SNAPSHOT)
    if flag != temporal.AVAILABLE:
        return None, flag, generated
    return data, flag, generated


def dated_field(
    value,
    data_date: str,
    cutoff_at: str,
    source: str,
    kind: str,
    data_time: str = "",
) -> Dict[str, Any]:
    flag = temporal.is_available(data_date, data_time, cutoff_at, kind)
    avail = temporal.available_at(data_date, data_time, kind)
    avail_s = temporal.iso(avail) if avail else ""
    event = temporal.event_time_for(data_date, kind)
    if flag == temporal.FUTURE:
        return provenance(
            None, data_date, source, "future",
            event_time=event, available_at=avail_s, temporal_state="future",
        )
    if flag == temporal.UNKNOWN:
        return provenance(
            None, data_date, source, "unknown",
            event_time=event, available_at=avail_s, temporal_state="unknown",
        )
    fresh = temporal.freshness(avail_s, cutoff_at)
    return provenance(
        value, data_date, source, fresh,
        event_time=event, available_at=avail_s,
        temporal_state=temporal.temporal_state_for(flag, fresh),
    )


def snapshot_field(value, generated_at: str, cutoff_at: str, source: str) -> Dict[str, Any]:
    if not generated_at:
        return provenance(None, "", source, "unknown", temporal_state="unknown")
    if not temporal.has_clock(generated_at):
        return provenance(
            None, generated_at[:10], source, "unknown",
            available_at="", temporal_state="unknown", source_as_of=generated_at,
        )
    flag = temporal.is_available(generated_at[:10], generated_at, cutoff_at, temporal.LATEST_SNAPSHOT)
    avail_s = temporal.iso(temporal.parse_dt(generated_at))
    if flag == temporal.FUTURE:
        return provenance(
            None, generated_at[:10], source, "future",
            event_time=avail_s, available_at=avail_s, temporal_state="future",
            source_as_of=generated_at,
        )
    if flag == temporal.UNKNOWN:
        return provenance(
            None, generated_at[:10], source, "unknown",
            event_time=avail_s, available_at=avail_s, temporal_state="unknown",
            source_as_of=generated_at,
        )
    fresh = temporal.freshness(avail_s, cutoff_at)
    return provenance(
        value, generated_at[:10], source, fresh,
        event_time=avail_s, available_at=avail_s,
        temporal_state=temporal.temporal_state_for(flag, fresh),
        source_as_of=generated_at,
    )


def last_available_row(rows, cutoff_at: str, kind: str, date_key: str = "date"):
    """rows: iterable of mapping with date. 返回 (row, day) 或 (None, '')."""
    available = []
    for row in rows:
        day = str(row.get(date_key) or "")[:10]
        if temporal.is_available(day, "", cutoff_at, kind) == temporal.AVAILABLE:
            available.append((day, row))
    if not available:
        return None, ""
    available.sort(key=lambda x: x[0])
    day, row = available[-1]
    return row, day


def repo_path(*parts: str) -> Path:
    return ROOT.joinpath(*parts)
