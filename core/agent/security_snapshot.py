"""单只证券的多源行情与本地技术面工具。"""
from __future__ import annotations

from core.agent.market_tools import expected_market_day
from core.calendar import refresh_trading_calendar
from core.ingest.live import refresh_instrument_quotes
from core.research.entity_resolver import resolve_with_network
from core.research.tools import get_market_data
from core.store import Store
from core.symbols import is_valid_code, normalize_code


def run(
    store: Store, message: str, route: dict, *, network: str = "replay",
    summary: dict | None = None,
) -> dict:
    summary = summary or {}
    routed = route.get("entity") or {}
    name = routed.get("name") or summary.get("entity_name") or summary.get("active_entity") or ""
    code = normalize_code(routed.get("code") or summary.get("entity_code") or "")
    entity = {}
    if not is_valid_code(code):
        query = name or message
        entity = resolve_with_network(query, network=network, store=store)
        if entity.get("status") == "RESOLVED":
            name = entity.get("canonical_name") or name
            code = normalize_code(entity.get("ticker") or "")
    if not is_valid_code(code):
        return {
            "ok": False, "status": "DATA_UNAVAILABLE", "error_code": "SYMBOL_UNRESOLVED",
            "answer": "我理解你在问价格或技术面，但还没可靠确认这家公司的股票代码。请补一个六位代码，我就直接查。",
            "entity_name": name, "entity_code": "",
        }

    refresh = None
    calendar = None
    if network == "live":
        calendar = refresh_trading_calendar()
        refresh = refresh_instrument_quotes(
            code, store=store, minimum_date=expected_market_day(), limit=250,
        )
    quote = get_market_data(code, store=store)
    if not quote.get("ok"):
        reason = (refresh.message if refresh is not None else quote.get("message")) or "行情不可用"
        return {
            "ok": False, "status": "DATA_UNAVAILABLE", "error_code": "MARKET_DATA_UNAVAILABLE",
            "answer": "已经确认 {0}（{1}），但没有拿到可用行情：{2}".format(name or "该公司", code, reason),
            "entity_name": name, "entity_code": code,
        }

    row = quote.get("row") or {}
    technical = quote.get("technical") or {}
    expected = expected_market_day()
    asof = row.get("date") or ""
    stale = bool(expected and (not asof or asof < expected))
    lines = [
        "# {0}（{1}）行情与技术面".format(name or "该公司", code),
        "行情：{0}，涨跌幅 {1}%（{2}{3}）".format(
            _value(row.get("close")), _value(row.get("pct_chg")), asof or "UNKNOWN",
            "，数据未达到最近交易日 " + expected if stale else "",
        ),
    ]
    if technical.get("ok"):
        ma = technical.get("ma") or {}
        macd = technical.get("macd") or {}
        range20 = technical.get("range_20d") or {}
        lines.extend([
            "趋势：{0}".format(technical.get("trend") or "UNKNOWN"),
            "均线：MA5 {0} / MA20 {1} / MA60 {2}".format(
                _value(ma.get("5")), _value(ma.get("20")), _value(ma.get("60")),
            ),
            "动量：20日 {0}% / 60日 {1}% / RSI14 {2} / MACD柱 {3}".format(
                _value(technical.get("return_20d_pct")), _value(technical.get("return_60d_pct")),
                _value(technical.get("rsi_14")), _value(macd.get("histogram")),
            ),
            "波动与位置：ATR14 {0}% / 20日区间 {1}～{2} / 当前位于区间 {3}%".format(
                _value(technical.get("atr_14_pct")), _value(range20.get("low")),
                _value(range20.get("high")), _value(range20.get("position_pct")),
            ),
            "量能：近5日均量 / 近20日均量 = {0}".format(
                _value(technical.get("volume_5d_vs_20d")),
            ),
        ])
    else:
        lines.append("技术指标：UNKNOWN（{0}）".format(technical.get("message") or "历史日线不足"))
    if refresh is not None:
        lines.append("数据链路：{0}".format(refresh.message))
    elif calendar and not calendar.get("ok"):
        lines.append("交易日历：动态更新失败，使用本地休市表。")
    lines.append("说明：技术指标由公开 OHLCV 本地计算，只描述历史价格行为，不构成买卖信号。")
    return {
        "ok": not stale,
        "status": "COMPLETED" if not stale else "DATA_STALE",
        "error_code": "" if not stale else "MARKET_DATA_STALE",
        "answer": "\n\n".join(lines),
        "entity_name": name, "entity_code": code,
        "market_data": {"row": row, "technical": technical, "expected_asof": expected, "stale": stale},
    }


def _value(value) -> str:
    if isinstance(value, float):
        return str(round(value, 2))
    return "UNKNOWN" if value is None else str(value)
