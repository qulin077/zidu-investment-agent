"""指数事实。不是涨跌建议。日线按 DAILY_CLOSE：早盘看不到当日收盘。"""
from __future__ import annotations

from typing import Any, Dict

from core.context import io
from core.store import Store

INDICES = (
    ("csi300", "沪深300", ("data/raw/policy/csi300.csv", "data/raw/rotation/csi300.csv"), "000300"),
    ("csi1000", "中证1000/全A", ("data/raw/policy/csi2000.csv", "data/raw/policy/ths_allA_eq.csv"), "000852"),
    ("chinext", "创业板", ("data/raw/policy/chinext.csv", "data/raw/rotation/chinext.csv"), "399006"),
    ("star50", "科创50", ("data/raw/policy/star50.csv", "data/raw/rotation/star50.csv"), "000688"),
)


def collect(cutoff_at: str, store: Store, decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    indices = {}
    source_refs = []
    freshness = "missing"
    coverage = "missing"
    for key, label, files, code in INDICES:
        series = io.store_closes(store, code)
        source = "quote_daily"
        if not series:
            for rel in files:
                series = io.read_csv_closes(io.repo_path(*rel.split("/")))
                if series:
                    source = rel
                    break
        daily = io.field_from_series(series, cutoff_at, source, key, 1)
        d5 = io.field_from_series(series, cutoff_at, source, key, 5)
        d20 = io.field_from_series(series, cutoff_at, source, key, 20)
        indices[key] = {
            "label": label,
            "daily_return": daily,
            "ret_5d": d5,
            "ret_20d": d20,
        }
        source_refs.append({"field": key, "source": source, "as_of": daily.get("as_of")})
        states = {daily["freshness"], d5["freshness"], d20["freshness"]}
        if "fresh" in states:
            freshness = "fresh" if freshness != "stale" else "stale"
            coverage = "full" if coverage != "partial" else "partial"
        elif "stale" in states:
            freshness = "stale"
            coverage = "partial"
        elif "future" in states and freshness == "missing":
            freshness = "future"
        elif "missing" in states and coverage == "missing":
            pass
        else:
            coverage = "partial"
    if any(v["daily_return"]["freshness"] == "fresh" for v in indices.values()):
        coverage = "full" if all(v["daily_return"]["value"] is not None for v in indices.values()) else "partial"
        freshness = "stale" if any(v["daily_return"]["freshness"] == "stale" for v in indices.values()) else "fresh"
    if all(v["daily_return"]["freshness"] == "missing" for v in indices.values()):
        coverage, freshness = "missing", "missing"
    elif all(v["daily_return"]["freshness"] == "future" for v in indices.values()):
        coverage, freshness = "missing", "future"
    return {
        "provider": "market",
        "status": "ok" if coverage != "missing" else "missing",
        "payload": {"indices": indices},
        "coverage": coverage,
        "freshness": freshness,
        "source_refs": source_refs,
    }
