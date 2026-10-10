"""Availability Policy t1。ENTRY_CONTEXT 只能用 cutoff 时已可得的数据。

event_time     数据描述的市场事件时间
available_at   系统认为用户何时可见
captured_at    冻结进 Context 的时刻
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

TEMPORAL_POLICY_VERSION = "t1"

AVAILABLE = "AVAILABLE"
FUTURE = "FUTURE"
UNKNOWN = "UNKNOWN"

DAILY_CLOSE = "DAILY_CLOSE"
PREVIOUS_US_CLOSE = "PREVIOUS_US_CLOSE"
END_OF_DAY_SENTIMENT = "END_OF_DAY_SENTIMENT"
LATEST_SNAPSHOT = "LATEST_SNAPSHOT"

CN_TZ = timezone(timedelta(hours=8))
CN_CLOSE_HOUR, CN_CLOSE_MINUTE = 15, 0
CN_SENTIMENT_HOUR, CN_SENTIMENT_MINUTE = 15, 30
STALE_DAYS = 3


def parse_dt(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    text = str(raw).strip().replace("Z", "+00:00").replace(" ", "T")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            if len(text) == 10:
                return datetime(int(text[:4]), int(text[5:7]), int(text[8:10]), tzinfo=CN_TZ)
            if "+" in text[10:] or text.endswith("Z"):
                dt = datetime.fromisoformat(text)
            else:
                body = text[:19] if len(text) >= 19 else text
                dt = datetime.fromisoformat(body)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CN_TZ)
            return dt.astimezone(CN_TZ)
        except ValueError:
            return None
    return None


def iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.astimezone(CN_TZ).isoformat(timespec="seconds")


def has_clock(raw: str) -> bool:
    text = str(raw or "").strip()
    if len(text) <= 10:
        return False
    return "T" in text or " " in text


def cutoff_date(cutoff_at: str) -> str:
    dt = parse_dt(cutoff_at)
    return dt.date().isoformat() if dt else (cutoff_at or "")[:10]


def available_at(data_date: str, data_time: str, data_kind: str) -> Optional[datetime]:
    kind = (data_kind or DAILY_CLOSE).upper()
    if kind == LATEST_SNAPSHOT:
        return parse_dt(data_time or data_date)
    day = parse_dt((data_date or "")[:10])
    if day is None:
        return parse_dt(data_time or data_date)
    if data_time and len(str(data_time)) > 10:
        stamped = parse_dt(data_time)
        if stamped is not None:
            return stamped
    if kind == END_OF_DAY_SENTIMENT:
        return day.replace(hour=CN_SENTIMENT_HOUR, minute=CN_SENTIMENT_MINUTE, second=0)
    if kind == PREVIOUS_US_CLOSE:
        return (day + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    return day.replace(hour=CN_CLOSE_HOUR, minute=CN_CLOSE_MINUTE, second=0)


def is_available(
    data_date: str,
    data_time: str,
    cutoff_at: str,
    data_kind: str,
) -> str:
    cutoff = parse_dt(cutoff_at)
    if cutoff is None:
        return UNKNOWN
    kind = (data_kind or DAILY_CLOSE).upper()
    if kind == PREVIOUS_US_CLOSE:
        day = (data_date or "")[:10]
        cd = cutoff.date().isoformat()
        if not day:
            return UNKNOWN
        if day < cd:
            return AVAILABLE
        return FUTURE
    avail = available_at(data_date, data_time, kind)
    if avail is None:
        return UNKNOWN
    if avail <= cutoff:
        return AVAILABLE
    return FUTURE


def freshness(available_at_raw: str, cutoff_at: str, stale_days: int = STALE_DAYS) -> str:
    cutoff = parse_dt(cutoff_at)
    avail = parse_dt(available_at_raw)
    if cutoff is None:
        return "unknown"
    if avail is None:
        return "missing" if not available_at_raw else "unknown"
    if avail > cutoff:
        return "future"
    age = (cutoff - avail).total_seconds() / 86400.0
    if age > stale_days:
        return "stale"
    return "fresh"


def temporal_state_for(avail_flag: str, freshness_value: str = "") -> str:
    if avail_flag == FUTURE or freshness_value == "future":
        return "future"
    if avail_flag == UNKNOWN or freshness_value in ("unknown", "missing"):
        return "unknown" if avail_flag == UNKNOWN or freshness_value == "unknown" else "missing"
    return "available"


def event_time_for(data_date: str, data_kind: str) -> str:
    kind = (data_kind or DAILY_CLOSE).upper()
    day = parse_dt((data_date or "")[:10])
    if day is None:
        return ""
    if kind == END_OF_DAY_SENTIMENT:
        return iso(day.replace(hour=CN_SENTIMENT_HOUR, minute=CN_SENTIMENT_MINUTE, second=0))
    if kind == PREVIOUS_US_CLOSE:
        return iso(day.replace(hour=16, minute=0, second=0))
    return iso(day.replace(hour=CN_CLOSE_HOUR, minute=CN_CLOSE_MINUTE, second=0))
