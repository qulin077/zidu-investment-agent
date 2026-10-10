"""交易日历与数据新鲜度判定的唯一出口。

替代散在 daily_update / validate_daily_data / stock_screener / personal_board /
account_snapshot_calc / trade_gate / trading_data_audit 里的七份新鲜度实现。

阈值统一按**自然日**计算，与既有七处实现口径一致（max_age_days=7）；
交易日相关函数基于周末加可选节假日表，仅用于推算下一交易日等场景。
"""
from __future__ import annotations

import math
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Iterable, Optional, Set

import yaml

from core.config import DATA_DIR, HOLIDAYS_YAML

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S")
_TRADING_CALENDAR_CACHE = DATA_DIR / "cache" / "trading_calendar.json"


def parse_date(value: Any) -> Optional[date]:
    """把数据里出现过的各种日期写法解析成 date；失败返回 None 而不是抛错。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat", "null"}:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text[: len(fmt) + 2].strip(), fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def today() -> date:
    return date.today()


def to_iso(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else ""


@lru_cache(maxsize=1)
def holidays() -> Set[date]:
    """A 股休市日。缺表时返回空集合，退化为仅按周末判断。"""
    if not HOLIDAYS_YAML.exists():
        return set()
    with HOLIDAYS_YAML.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    out = set()
    for item in data.get("closed") or []:
        parsed = parse_date(item)
        if parsed:
            out.add(parsed)
    return out


@lru_cache(maxsize=1)
def cached_trading_days() -> Set[date]:
    """读取免费交易日历缓存。损坏或缺失时安全退化。"""
    if not _TRADING_CALENDAR_CACHE.is_file():
        return set()
    try:
        payload = json.loads(_TRADING_CALENDAR_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    result = set()
    for value in payload.get("trading_days") or []:
        parsed = parse_date(value)
        if parsed:
            result.add(parsed)
    return result


def refresh_trading_calendar(max_age_days: int = 7, fetcher=None) -> dict:
    """通过 AKShare 免费日历更新本地缓存；失败不改变现有日历。"""
    if _TRADING_CALENDAR_CACHE.is_file():
        age = (time.time() - _TRADING_CALENDAR_CACHE.stat().st_mtime) / 86400.0
        if age <= max(0, max_age_days):
            rows = cached_trading_days()
            if rows:
                return {"ok": True, "cached": True, "count": len(rows)}
    try:
        if fetcher is None:
            import akshare as ak
            frame = ak.tool_trade_date_hist_sina()
            values = frame["trade_date"].tolist()
        else:
            values = fetcher()
        days = sorted({to_iso(value) for value in values if to_iso(value)})
        if not days:
            raise ValueError("交易日历为空")
        payload = {
            "source": "akshare.tool_trade_date_hist_sina",
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "trading_days": days,
        }
        _TRADING_CALENDAR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _TRADING_CALENDAR_CACHE.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8",
        )
        cached_trading_days.cache_clear()
        return {"ok": True, "cached": False, "count": len(days)}
    except Exception as exc:
        return {"ok": False, "cached": False, "count": 0, "error": str(exc)}


def is_trading_day(value: Any) -> bool:
    day = parse_date(value)
    if day is None:
        return False
    known = cached_trading_days()
    if known and min(known) <= day <= max(known):
        return day in known
    return day.weekday() < 5 and day not in holidays()


def previous_trading_day(value: Any, skip: int = 1) -> Optional[date]:
    day = parse_date(value)
    if day is None:
        return None
    remaining = max(1, skip)
    while remaining > 0:
        day -= timedelta(days=1)
        if is_trading_day(day):
            remaining -= 1
    return day


def next_trading_day(value: Any, skip: int = 1) -> Optional[date]:
    day = parse_date(value)
    if day is None:
        return None
    remaining = max(1, skip)
    while remaining > 0:
        day += timedelta(days=1)
        if is_trading_day(day):
            remaining -= 1
    return day


def age_days(asof: Any, ref: Any = None) -> Optional[int]:
    """asof 距参考日的自然日数。未来日期返回负数，无法解析返回 None。"""
    start = parse_date(asof)
    if start is None:
        return None
    end = parse_date(ref) or today()
    return (end - start).days


@dataclass(frozen=True)
class FreshnessResult:
    ok: bool
    age: Optional[int]
    asof: str
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class Freshness:
    """一个数据集允许多旧的声明。放进 contracts，由校验层统一执行。"""

    max_age_days: int = 7
    allow_future: bool = False
    label: str = ""

    def check(self, asof: Any, ref: Any = None) -> FreshnessResult:
        iso = to_iso(asof)
        age = age_days(asof, ref)
        if age is None:
            return FreshnessResult(False, None, iso, "无法解析日期")
        if age < 0 and not self.allow_future:
            return FreshnessResult(False, age, iso, "日期晚于参考日 {0} 天".format(-age))
        if age > self.max_age_days:
            return FreshnessResult(
                False, age, iso, "已过期 {0} 天，阈值 {1} 天".format(age, self.max_age_days)
            )
        return FreshnessResult(True, age, iso)


DEFAULT_QUOTE_FRESHNESS = Freshness(max_age_days=7, label="行情")
DEFAULT_NEWS_FRESHNESS = Freshness(max_age_days=3, label="新闻")


def coverage_ok(success: int, requested: int, min_ratio: float = 0.9) -> bool:
    """覆盖率闸门。沿用 daily_update.quote_coverage_ok 的口径。"""
    if requested <= 0:
        return False
    return success >= max(1, math.ceil(requested * min_ratio))


def latest(values: Iterable[Any], not_after: Any = None) -> Optional[date]:
    """一组日期里不晚于 not_after 的最大值，用于防止历史视图读到未来数据。"""
    ceiling = parse_date(not_after)
    best: Optional[date] = None
    for value in values:
        parsed = parse_date(value)
        if parsed is None:
            continue
        if ceiling is not None and parsed > ceiling:
            continue
        if best is None or parsed > best:
            best = parsed
    return best
