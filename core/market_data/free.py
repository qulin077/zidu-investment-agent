"""无需账号的 A 股行情 Provider。

当前顺序：

* 快照：新浪 -> 腾讯
* 历史前复权日线：腾讯 -> 东方财富

这些都是公开网页接口，适合个人项目和降级链路，但没有商业 SLA。调用方必须
继续执行日期、新鲜度和覆盖率检查，不能因为 HTTP 成功就认为行情可用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Iterable, List, Optional

from core.calendar import to_iso
from core.http import DEFAULT_CLIENT, HttpClient
from core.ingest.base import as_float
from core.symbols import is_valid_code, market_prefix, normalize_code, tencent_symbol

SINA_QUOTE_URL = "https://hq.sinajs.cn/list={0}"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q={0}"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

SINA_CLIENT = HttpClient(referer="https://finance.sina.com.cn/")
TENCENT_CLIENT = HttpClient(referer="https://stockapp.finance.qq.com/")
EASTMONEY_CLIENT = HttpClient(referer="https://quote.eastmoney.com/")


@dataclass
class MarketFetch:
    rows: List[Dict[str, Any]] = field(default_factory=list)
    providers: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)


def sina_snapshots(codes: Iterable[str], client: HttpClient = SINA_CLIENT) -> List[Dict[str, Any]]:
    targets = _targets(codes)
    if not targets:
        return []
    symbols = [tencent_symbol(code) for code in targets]
    text = client.get(
        SINA_QUOTE_URL.format(",".join(symbols)), encoding="gbk", timeout=10, attempts=2,
    )
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        if '="' not in line:
            continue
        left, _, raw = line.partition('="')
        code = normalize_code(left.rsplit("_", 1)[-1])
        parts = raw.rstrip('";').split(",")
        if code not in targets or len(parts) < 32:
            continue
        previous = as_float(parts[2])
        close = as_float(parts[3])
        day = to_iso(parts[30])
        if not day or close is None or close <= 0:
            continue
        rows.append(_bar(
            code, day, parts[1], close, parts[4], parts[5], parts[8],
            _pct(close, previous), provider="sina",
        ))
    return rows


def tencent_snapshots(codes: Iterable[str], client: HttpClient = TENCENT_CLIENT) -> List[Dict[str, Any]]:
    targets = _targets(codes)
    if not targets:
        return []
    symbols = [tencent_symbol(code) for code in targets]
    text = client.get(
        TENCENT_QUOTE_URL.format(",".join(symbols)), encoding="gbk", timeout=10, attempts=2,
    )
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        if '="' not in line:
            continue
        left, _, raw = line.partition('="')
        code = normalize_code(left.rsplit("_", 1)[-1])
        parts = raw.rstrip('";').split("~")
        if code not in targets or len(parts) < 38:
            continue
        close = as_float(parts[3])
        previous = as_float(parts[4])
        stamp = re.sub(r"\D", "", parts[30] or "")
        day = to_iso(stamp[:8]) if len(stamp) >= 8 else ""
        if not day or close is None or close <= 0:
            continue
        rows.append(_bar(
            code, day, parts[5], close, parts[33], parts[34], parts[36],
            as_float(parts[32]) if as_float(parts[32]) is not None else _pct(close, previous),
            provider="tencent",
        ))
    return rows


def tencent_daily_bars(
    code: str, limit: int = 250, client: HttpClient = DEFAULT_CLIENT,
) -> List[Dict[str, Any]]:
    symbol = tencent_symbol(code)
    payload = client.get_json(
        TENCENT_KLINE_URL,
        params={"param": "{0},day,,,{1},qfq".format(symbol, max(5, int(limit)))},
    )
    node = (payload.get("data") or {}).get(symbol) or {}
    bars = node.get("qfqday") or node.get("day") or []
    return _normalize_bars(code, bars, provider="tencent")


def eastmoney_daily_bars(
    code: str, limit: int = 250, client: HttpClient = EASTMONEY_CLIENT,
) -> List[Dict[str, Any]]:
    norm = normalize_code(code)
    secid = "{0}.{1}".format(1 if market_prefix(norm) == "sh" else 0, norm)
    payload = client.get_json(
        EASTMONEY_KLINE_URL,
        params={
            "secid": secid, "klt": 101, "fqt": 1, "lmt": max(5, int(limit)),
            "end": "20500101", "iscca": 1,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        },
    )
    raw = ((payload.get("data") or {}).get("klines") or [])
    bars = [str(row).split(",") for row in raw]
    return _normalize_bars(code, bars, provider="eastmoney", pct_index=8)


class FreeMarketDataGateway:
    """Provider 顺序和失败隔离都集中在这里。"""

    def __init__(
        self, *, sina_client: HttpClient = SINA_CLIENT,
        tencent_client: HttpClient = TENCENT_CLIENT,
        history_client: HttpClient = DEFAULT_CLIENT,
        eastmoney_client: HttpClient = EASTMONEY_CLIENT,
    ) -> None:
        self.sina_client = sina_client
        self.tencent_client = tencent_client
        self.history_client = history_client
        self.eastmoney_client = eastmoney_client

    def snapshots(self, codes: Iterable[str], minimum_date: str = "") -> MarketFetch:
        targets = _targets(codes)
        chosen: Dict[str, Dict[str, Any]] = {}
        providers: List[str] = []
        errors: List[str] = []
        lanes = (
            ("sina", lambda rows: sina_snapshots(rows, self.sina_client)),
            ("tencent", lambda rows: tencent_snapshots(rows, self.tencent_client)),
        )
        for name, fetch in lanes:
            missing = [code for code in targets if code not in chosen]
            if not missing:
                break
            try:
                rows = fetch(missing)
            except Exception as exc:  # 一个免费源失败不能取消整批。
                errors.append("{0}: {1}".format(name, exc))
                continue
            accepted = 0
            for row in rows:
                if minimum_date and (row.get("date") or "") < minimum_date:
                    continue
                code = row.get("code") or ""
                if code in missing:
                    chosen[code] = row
                    accepted += 1
            if accepted:
                providers.append(name)
        missing = [code for code in targets if code not in chosen]
        return MarketFetch(
            rows=[chosen[code] for code in targets if code in chosen],
            providers=providers, errors=errors, missing=missing,
        )

    def daily_bars(self, code: str, limit: int = 250) -> MarketFetch:
        norm = normalize_code(code)
        errors: List[str] = []
        lanes = (
            ("tencent", lambda: tencent_daily_bars(norm, limit, self.history_client)),
            ("eastmoney", lambda: eastmoney_daily_bars(norm, limit, self.eastmoney_client)),
        )
        for name, fetch in lanes:
            try:
                rows = fetch()
            except Exception as exc:
                errors.append("{0}: {1}".format(name, exc))
                continue
            if rows:
                return MarketFetch(rows=rows, providers=[name], errors=errors)
            errors.append("{0}: 无日线返回".format(name))
        return MarketFetch(rows=[], providers=[], errors=errors, missing=[norm])


def _targets(codes: Iterable[str]) -> List[str]:
    result: List[str] = []
    for value in codes:
        code = normalize_code(value)
        if is_valid_code(code) and code not in result:
            result.append(code)
    return result


def _normalize_bars(
    code: str, bars: Iterable[Any], *, provider: str, pct_index: Optional[int] = None,
) -> List[Dict[str, Any]]:
    norm = normalize_code(code)
    rows: List[Dict[str, Any]] = []
    previous_close: Optional[float] = None
    for raw in bars:
        bar = list(raw) if not isinstance(raw, str) else raw.split(",")
        if len(bar) < 6:
            continue
        day = to_iso(bar[0])
        close = as_float(bar[2])
        if not day or close is None or close <= 0:
            continue
        pct = as_float(bar[pct_index]) if pct_index is not None and len(bar) > pct_index else None
        if pct is None:
            pct = _pct(close, previous_close)
        rows.append(_bar(norm, day, bar[1], close, bar[3], bar[4], bar[5], pct, provider))
        previous_close = close
    rows.sort(key=lambda row: row.get("date") or "")
    return rows


def _bar(code, day, open_, close, high, low, volume, pct, provider) -> Dict[str, Any]:
    # ``provider`` 是运行态元数据，不会写入旧 quote_daily 表。
    return {
        "code": normalize_code(code), "date": day,
        "open": as_float(open_), "close": as_float(close),
        "high": as_float(high), "low": as_float(low),
        "volume": as_float(volume), "pct_chg": as_float(pct),
        "_provider": provider,
    }


def _pct(close: Optional[float], previous: Optional[float]) -> Optional[float]:
    if close is None or previous in (None, 0):
        return None
    return (close - previous) / previous * 100.0
