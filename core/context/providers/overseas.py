"""海外稳定字段。US 日线 V0：只允许严格早于 China cutoff_date。"""
from __future__ import annotations

from typing import Any, Dict

from core.context import io, temporal
from core.store import Store

US_FILES = {
    "nasdaq_qqq": ("QQQ", "data/raw/quotes_us/QQQ.csv"),
    "sox": ("SOXX", "data/raw/quotes_us/SOXX.csv"),
    "nvda": ("NVDA", "data/raw/quotes_us/NVDA.csv"),
}
MACRO = io.repo_path("data", "raw", "macro", "macro_latest.json")


def collect(cutoff_at: str, store: Store, decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    refs = []
    states = []
    for key, (code, rel) in US_FILES.items():
        series = io.store_closes(store, code) or io.read_csv_closes(io.repo_path(*rel.split("/")))
        field = io.field_from_series(series, cutoff_at, rel, key, 5, kind=temporal.PREVIOUS_US_CLOSE)
        payload["{0}_5d_return".format(key)] = field
        refs.append({"field": key, "source": rel, "as_of": field.get("as_of")})
        states.append(field["freshness"])
    macro, macro_flag, macro_gen = io.load_latest(MACRO, cutoff_at)
    rates = (macro or {}).get("rates") or {}
    fx = (macro or {}).get("fx") or {}
    for key, block, source in (
        ("vix", rates.get("vix") or {}, "macro_latest.json"),
        ("us10y", rates.get("us10y") or {}, "macro_latest.json"),
        ("dxy", fx.get("dxy") or {}, "macro_latest.json"),
    ):
        if macro_flag != temporal.AVAILABLE:
            payload[key] = io.snapshot_field(None, macro_gen, cutoff_at, source)
            refs.append({"field": key, "source": source, "as_of": ""})
            states.append(payload[key]["freshness"])
            continue
        day = str(block.get("date") or "")[:10]
        # 块日期按美股日线保守规则；文件 generated_at 已通过
        field = io.dated_field(block.get("value"), day, cutoff_at, source, temporal.PREVIOUS_US_CLOSE)
        payload[key] = field
        refs.append({"field": key, "source": source, "as_of": day})
        states.append(field["freshness"])
    if not states or all(s == "missing" for s in states):
        coverage, freshness, status = "missing", "missing", "missing"
    elif all(s == "future" for s in states):
        coverage, freshness, status = "missing", "future", "missing"
    elif "failed" in states:
        coverage, freshness, status = "partial", "stale", "failed"
    elif all(s == "fresh" for s in states):
        coverage, freshness, status = "full", "fresh", "ok"
    elif "stale" in states:
        coverage, freshness, status = "partial", "stale", "ok"
    else:
        coverage, freshness, status = "partial", "missing", "ok"
    return {
        "provider": "overseas",
        "status": status,
        "payload": payload,
        "coverage": coverage,
        "freshness": freshness,
        "source_refs": refs,
    }
