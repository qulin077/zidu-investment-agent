"""实时行情采集。

兼容原有函数入口；产品运行时使用 iFinD 优先、免费公开行情降级的统一网关。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from core.http import DEFAULT_CLIENT, HttpClient
from core.ingest.base import IngestResult
from core.market_data.free import (
    FreeMarketDataGateway,
    SINA_CLIENT,
    TENCENT_CLIENT,
    sina_snapshots,
    tencent_daily_bars,
)
from core.market_data.ifind import MarketDataGateway
from core.store import STORE, Store
from core.symbols import is_valid_code, normalize_code, universe_codes

_SINA = SINA_CLIENT


def fetch_daily_bars(
    code: str, limit: int = 120, client: HttpClient = DEFAULT_CLIENT
) -> List[Dict[str, Any]]:
    """腾讯前复权日线；保留旧入口供脚本和测试调用。"""
    return [_storage_row(row) for row in tencent_daily_bars(code, limit=limit, client=client)]


def fetch_sina_snapshots(
    codes: Iterable[str], client: HttpClient = _SINA,
) -> List[Dict[str, Any]]:
    """批量读取新浪最新行情；保留旧入口。"""
    return [_storage_row(row) for row in sina_snapshots(codes, client=client)]


def refresh_latest_quotes(
    codes: Optional[Iterable[str]] = None,
    store: Store = STORE,
    client: HttpClient = _SINA,
    fallback_client: HttpClient = TENCENT_CLIENT,
    minimum_date: str = "",
    gateway=None,
) -> IngestResult:
    """批量刷新快照；iFinD 缺失时逐标的降级到新浪、腾讯。"""
    targets = [normalize_code(c) for c in (codes if codes is not None else universe_codes())]
    targets = [c for c in targets if is_valid_code(c)]
    result = IngestResult(dataset="quote_daily")
    if not targets:
        result.ok = False
        result.message = "股票池为空"
        return result
    source = gateway or MarketDataGateway(fallback=FreeMarketDataGateway(
        sina_client=client, tencent_client=fallback_client,
    ))
    fetched = source.snapshots(targets, minimum_date=minimum_date)
    payload = [_storage_row(row) for row in fetched.rows]
    returned = {row["code"] for row in payload}
    result.skipped = list(fetched.missing)
    result.skipped.extend(fetched.errors[:5])
    result.rows = store.upsert("quote_daily", payload)
    result.asof = max((row["date"] for row in payload), default="")
    succeeded = len(returned)
    result.ok = succeeded >= max(1, int(len(targets) * 0.9))
    providers = "+".join(fetched.providers) or "无可用源"
    result.message = "行情 {0}，快照 {1}/{2}".format(providers, succeeded, len(targets))
    if not result.ok:
        result.message += "，低于 90% 覆盖率阈值"
    return result


def refresh_quotes(
    codes: Optional[Iterable[str]] = None,
    limit: int = 120,
    store: Store = STORE,
    client: HttpClient = DEFAULT_CLIENT,
) -> IngestResult:
    """拉取池内前复权日线；腾讯失败时按标的降级到东方财富。"""
    targets = [normalize_code(c) for c in (codes if codes is not None else universe_codes())]
    targets = [c for c in targets if is_valid_code(c)]
    result = IngestResult(dataset="quote_daily")
    if not targets:
        result.ok = False
        result.message = "股票池为空"
        return result

    payload: List[Dict[str, Any]] = []
    latest = ""
    providers = set()
    gateway = FreeMarketDataGateway(history_client=client)
    for code in targets:
        fetched = gateway.daily_bars(code, limit=limit)
        bars = [_storage_row(row) for row in fetched.rows]
        if not bars:
            detail = "；".join(fetched.errors[-2:]) or "无K线返回"
            result.skipped.append("{0}: {1}".format(code, detail))
            continue
        providers.update(fetched.providers)
        payload.extend(bars)
        latest = max(latest, bars[-1]["date"])

    result.rows = store.upsert("quote_daily", payload)
    result.asof = latest
    succeeded = len(targets) - len(result.skipped)
    result.ok = succeeded >= max(1, int(len(targets) * 0.9))
    if not result.ok:
        result.message = "成功 {0}/{1}，低于 90% 覆盖率阈值".format(succeeded, len(targets))
    else:
        result.message = "免费日线 {0}，成功 {1}/{2}".format(
            "+".join(sorted(providers)) or "UNKNOWN", succeeded, len(targets),
        )
    return result


def refresh_instrument_quotes(
    code: str, *, limit: int = 250, store: Store = STORE,
    gateway=None, minimum_date: str = "",
) -> IngestResult:
    """刷新任意一只已解析 A 股，不要求它预先存在于自选股票池。"""
    norm = normalize_code(code)
    result = IngestResult(dataset="quote_daily")
    if not is_valid_code(norm):
        result.ok = False
        result.message = "无效股票代码：{0}".format(code)
        return result
    source = gateway or MarketDataGateway()
    history = source.daily_bars(norm, limit=limit)
    snapshot = source.snapshots([norm], minimum_date=minimum_date)
    merged = {row.get("date"): _storage_row(row) for row in history.rows if row.get("date")}
    for row in snapshot.rows:
        if row.get("date"):
            merged[row["date"]] = _storage_row(row)
    rows = [merged[key] for key in sorted(merged)]
    result.rows = store.upsert("quote_daily", rows) if rows else 0
    result.asof = rows[-1]["date"] if rows else ""
    result.ok = bool(rows) and (not minimum_date or result.asof >= minimum_date)
    providers = list(dict.fromkeys(history.providers + snapshot.providers))
    errors = history.errors + snapshot.errors
    result.skipped = errors[:10]
    result.message = "行情 {0}，写入 {1} 条，截止 {2}".format(
        "+".join(providers) or "无可用源", result.rows, result.asof or "UNKNOWN",
    )
    if not result.ok and errors:
        result.message += "；" + "；".join(errors[-2:])
    return result


def _storage_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {key: row.get(key) for key in (
        "code", "date", "open", "high", "low", "close", "volume", "pct_chg",
    )}
