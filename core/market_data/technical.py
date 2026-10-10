"""从已落库 OHLCV 本地计算技术面快照。

不调用模型、不依赖第三方指标服务，也不生成买卖信号。输出只描述价格、趋势、
动量和波动所处的客观位置。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def technical_snapshot(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    bars = [dict(row) for row in rows if _number(row.get("close")) is not None]
    bars.sort(key=lambda row: row.get("date") or "")
    if not bars:
        return {"ok": False, "message": "没有可计算的日线"}
    closes = [float(row["close"]) for row in bars]
    highs = [_number(row.get("high")) for row in bars]
    lows = [_number(row.get("low")) for row in bars]
    volumes = [_number(row.get("volume")) for row in bars]
    close = closes[-1]
    ma = {str(period): _sma(closes, period) for period in (5, 10, 20, 60)}
    dif, dea, histogram = _macd(closes)
    rsi = _rsi(closes, 14)
    atr = _atr(highs, lows, closes, 14)
    high20 = max((value for value in highs[-20:] if value is not None), default=None)
    low20 = min((value for value in lows[-20:] if value is not None), default=None)
    position20 = None
    if high20 is not None and low20 is not None and high20 != low20:
        position20 = (close - low20) / (high20 - low20) * 100.0
    volume5 = _avg([value for value in volumes[-5:] if value is not None])
    volume20 = _avg([value for value in volumes[-20:] if value is not None])
    volume_ratio = volume5 / volume20 if volume5 is not None and volume20 else None
    trend = _trend(close, ma)
    momentum = _momentum(rsi, dif, dea)
    return {
        "ok": True,
        "asof": bars[-1].get("date") or "",
        "bars": len(bars),
        "close": _round(close),
        "ma": {key: _round(value) for key, value in ma.items()},
        "return_20d_pct": _round(_return(closes, 20)),
        "return_60d_pct": _round(_return(closes, 60)),
        "macd": {"dif": _round(dif), "dea": _round(dea), "histogram": _round(histogram)},
        "rsi_14": _round(rsi),
        "atr_14": _round(atr),
        "atr_14_pct": _round(atr / close * 100.0 if atr is not None and close else None),
        "range_20d": {
            "high": _round(high20), "low": _round(low20),
            "position_pct": _round(position20),
        },
        "volume_5d_vs_20d": _round(volume_ratio),
        "trend": trend,
        "momentum": momentum,
        "disclaimer": "技术指标由公开 OHLCV 本地计算，只描述历史价格行为，不构成买卖信号。",
    }


def _trend(close: float, ma: Dict[str, Optional[float]]) -> str:
    ma5, ma20, ma60 = ma.get("5"), ma.get("20"), ma.get("60")
    if ma5 is not None and ma20 is not None and ma60 is not None:
        if close > ma5 > ma20 > ma60:
            return "多周期均线向上排列"
        if close < ma5 < ma20 < ma60:
            return "多周期均线向下排列"
    if ma20 is None:
        return "样本不足，尚不能判断中期趋势"
    return "价格位于20日均线上方" if close >= ma20 else "价格位于20日均线下方"


def _momentum(rsi: Optional[float], dif: Optional[float], dea: Optional[float]) -> str:
    parts: List[str] = []
    if rsi is not None:
        if rsi >= 70:
            parts.append("RSI处于偏高区间")
        elif rsi <= 30:
            parts.append("RSI处于偏低区间")
        else:
            parts.append("RSI处于中性区间")
    if dif is not None and dea is not None:
        parts.append("MACD动量为正" if dif >= dea else "MACD动量为负")
    return "；".join(parts) if parts else "样本不足"


def _sma(values: List[float], period: int) -> Optional[float]:
    return _avg(values[-period:]) if len(values) >= period else None


def _ema_series(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


def _macd(values: List[float]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    if len(values) < 2:
        return None, None, None
    ema12 = _ema_series(values, 12)
    ema26 = _ema_series(values, 26)
    difs = [left - right for left, right in zip(ema12, ema26)]
    dea = _ema_series(difs, 9)
    return difs[-1], dea[-1], (difs[-1] - dea[-1]) * 2.0


def _rsi(values: List[float], period: int) -> Optional[float]:
    if len(values) <= period:
        return None
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _atr(
    highs: List[Optional[float]], lows: List[Optional[float]],
    closes: List[float], period: int,
) -> Optional[float]:
    ranges: List[float] = []
    for index in range(1, len(closes)):
        high, low = highs[index], lows[index]
        if high is None or low is None:
            continue
        previous = closes[index - 1]
        ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
    if len(ranges) < period:
        return None
    value = sum(ranges[:period]) / period
    for item in ranges[period:]:
        value = (value * (period - 1) + item) / period
    return value


def _return(values: List[float], sessions: int) -> Optional[float]:
    if len(values) <= sessions or values[-sessions - 1] == 0:
        return None
    return (values[-1] / values[-sessions - 1] - 1.0) * 100.0


def _avg(values: List[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    return round(value, digits) if value is not None else None
