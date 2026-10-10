"""只围绕 Decision 所属 sector。映射不确定则 unknown / abstain。"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.context import io, temporal
from core.context.schema import provenance
from core.store import Store
from core.symbols import normalize_code, universe_index

ROTATION = io.repo_path("data", "raw", "rotation", "latest_rotation.json")


def collect(cutoff_at: str, store: Store, decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    code = normalize_code((decision or {}).get("code") or "")
    inst = universe_index().get(code)
    if inst is None or not inst.sector:
        return {
            "provider": "sector",
            "status": "unknown",
            "payload": {"sector": provenance("unknown", "", "universe.yaml", "missing")},
            "coverage": "missing",
            "freshness": "missing",
            "source_refs": [],
        }
    peers = [i.code for i in universe_index().values() if i.sector == inst.sector]
    series_list: List[List[Tuple[str, float]]] = []
    source = "quote_daily"
    for peer in peers:
        series = io.store_closes(store, peer)
        if not series:
            csv = io.read_csv_closes(io.repo_path("data", "raw", "quotes", "{0}.csv".format(peer)))
            if csv:
                series = csv
                source = "data/raw/quotes"
        if series:
            series_list.append(series)
    if not series_list:
        return {
            "provider": "sector",
            "status": "missing",
            "payload": {"sector": provenance(inst.sector, "", "universe.yaml", "missing")},
            "coverage": "missing",
            "freshness": "missing",
            "source_refs": [{"field": "sector", "source": "universe.yaml", "as_of": ""}],
        }
    rets_1, rets_5, days = [], [], []
    for series in series_list:
        stats = io.window_returns(series, cutoff_at)
        if not stats:
            continue
        days.append(stats["as_of"])
        if stats.get("ret_1d") is not None:
            rets_1.append(stats["ret_1d"])
        if stats.get("ret_5d") is not None:
            rets_5.append(stats["ret_5d"])
    day = max(days) if days else ""
    freshness = io._freshness(day, cutoff_at) if day else "missing"
    bench = io.store_closes(store, "000300") or io.read_csv_closes(io.repo_path("data", "raw", "policy", "csi300.csv"))
    bench_stats = io.window_returns(bench, cutoff_at) if bench else {}
    sector_5 = round(sum(rets_5) / len(rets_5), 4) if rets_5 else None
    bench_5 = bench_stats.get("ret_5d")
    rs = None if sector_5 is None or bench_5 is None else round(sector_5 - bench_5, 4)
    rot_data, _flag, rot_gen = io.load_latest(ROTATION, cutoff_at)
    bank = ((rot_data.get("bank_trend") or {}).get("level")) if rot_data else None
    payload = {
        "sector": (
            io.dated_field(inst.sector, day, cutoff_at, "universe.yaml", temporal.DAILY_CLOSE)
            if day else provenance(inst.sector, "", "universe.yaml", "missing")
        ),
        "sector_daily_return": io.dated_field(
            round(sum(rets_1) / len(rets_1), 4) if rets_1 else None,
            day, cutoff_at, source, temporal.DAILY_CLOSE,
        ),
        "sector_5d": io.dated_field(sector_5, day, cutoff_at, source, temporal.DAILY_CLOSE),
        "sector_vs_csi300_5d": io.dated_field(rs, day, cutoff_at, source, temporal.DAILY_CLOSE),
        "bank_b_level": io.snapshot_field(bank, rot_gen, cutoff_at, "latest_rotation.json"),
    }
    return {
        "provider": "sector",
        "status": "ok",
        "payload": payload,
        "coverage": "full" if freshness == "fresh" and rs is not None else "partial",
        "freshness": freshness,
        "source_refs": [{"field": "sector", "source": source, "as_of": day}],
    }
