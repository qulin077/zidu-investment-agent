"""Deterministic, read-only Context builder。不得改 Decision，不得写 Attribution。"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Optional

from core.context import inspect as ctx_inspect
from core.context import temporal
from core.context.providers import breadth, flow, market, overseas, sector, sentiment
from core.context.schema import CONTEXT_VERSION, KEY_PROVIDERS
from core.store import Store

ProviderFn = Callable[[str, Store, Optional[Dict[str, Any]]], Dict[str, Any]]

DEFAULT_PROVIDERS: Dict[str, ProviderFn] = {
    "market": market.collect,
    "breadth": breadth.collect,
    "sentiment": sentiment.collect,
    "sector": sector.collect,
    "overseas": overseas.collect,
    "flow": flow.collect,
}


def _forced_failures() -> set:
    raw = os.environ.get("CONTEXT_FAIL_PROVIDERS") or ""
    return {p.strip() for p in raw.split(",") if p.strip()}


def build(
    decision: Dict[str, Any],
    cutoff_at: str,
    store: Store,
    providers: Optional[Dict[str, ProviderFn]] = None,
    fail_providers: Optional[set] = None,
) -> Dict[str, Any]:
    """纯函数：相同输入得到相同 payload（不含 created_at / captured_at）。"""
    fail = set(fail_providers or ()) | _forced_failures()
    used = providers or DEFAULT_PROVIDERS
    results: Dict[str, Any] = {}
    coverage: Dict[str, str] = {}
    freshness: Dict[str, str] = {}
    status: Dict[str, str] = {}
    refs = []
    stamp = cutoff_at or ""
    for name, fn in used.items():
        if name in fail:
            results[name] = {}
            coverage[name] = "missing"
            freshness[name] = "missing"
            status[name] = "failed"
            continue
        try:
            out = fn(stamp, store, decision)
        except Exception as exc:  # noqa: BLE001 — provider 失败不得阻断 Decision
            results[name] = {"error": str(exc)}
            coverage[name] = "missing"
            freshness[name] = "missing"
            status[name] = "failed"
            continue
        results[name] = out.get("payload") or {}
        coverage[name] = out.get("coverage") or "missing"
        freshness[name] = out.get("freshness") or "missing"
        status[name] = out.get("status") or "ok"
        refs.extend(out.get("source_refs") or [])
    key_full = all(coverage.get(k) == "full" for k in KEY_PROVIDERS)
    overall = "full" if key_full and all(s != "failed" for s in status.values()) else "partial"
    regime = ""
    stage = ((results.get("sentiment") or {}).get("mkt_stage") or {}).get("value")
    if stage:
        regime = str(stage)
    payload = {
        "context_version": CONTEXT_VERSION,
        "temporal_policy_version": temporal.TEMPORAL_POLICY_VERSION,
        "cutoff_at": stamp,
        "as_of": temporal.cutoff_date(stamp),
        "market_regime": regime,
        "index_snapshot": results.get("market") or {},
        "sector_snapshot": results.get("sector") or {},
        "breadth_snapshot": results.get("breadth") or {},
        "sentiment_snapshot": results.get("sentiment") or {},
        "flow_snapshot": results.get("flow") or {},
        "overseas_snapshot": results.get("overseas") or {},
        "data_coverage": coverage,
        "data_freshness": freshness,
        "provider_status": status,
        "source_refs": refs,
        "coverage": overall,
    }
    payload["future_rejected_count"] = ctx_inspect.count_future(payload)
    return payload


def dumps(payload: Dict[str, Any]) -> Dict[str, str]:
    def enc(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)

    return {
        "index_snapshot_json": enc(payload.get("index_snapshot") or {}),
        "sector_snapshot_json": enc(payload.get("sector_snapshot") or {}),
        "breadth_snapshot_json": enc(payload.get("breadth_snapshot") or {}),
        "sentiment_snapshot_json": enc(payload.get("sentiment_snapshot") or {}),
        "flow_snapshot_json": enc(payload.get("flow_snapshot") or {}),
        "overseas_snapshot_json": enc(payload.get("overseas_snapshot") or {}),
        "data_freshness_json": enc(payload.get("data_freshness") or {}),
        "data_coverage_json": enc(payload.get("data_coverage") or {}),
        "source_refs_json": enc(payload.get("source_refs") or []),
        "provider_status_json": enc(payload.get("provider_status") or {}),
    }
