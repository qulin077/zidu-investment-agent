"""Context snapshot 存取。写入后不可静默覆盖。retry 只加 version，保留 captured_at 与 cutoff_at。"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from core.context import builder
from core.context import inspect as ctx_inspect
from core.context import temporal
from core.context.cutoff import resolve_cutoff
from core.context.schema import CONTEXT_VERSION, ENTRY_CONTEXT, REVIEW_CONTEXT
from core.product import pipeline
from core.review import flags, repo
from core.store import STORE, Store


def _next_id(store: Store) -> str:
    return "CX-{0:04d}".format(repo._next_seq(store, "decision_context_snapshot", "CX-"))


def latest(decision_id: str, snapshot_type: str, store: Store = STORE) -> Optional[Dict[str, Any]]:
    rows = store.query(
        "SELECT * FROM decision_context_snapshot WHERE decision_id = ? AND snapshot_type = ?"
        " ORDER BY snapshot_version DESC LIMIT 1",
        (decision_id, snapshot_type),
    )
    return rows[0] if rows else None


def list_for(decision_id: str, store: Store = STORE):
    return store.query(
        "SELECT * FROM decision_context_snapshot WHERE decision_id = ?"
        " ORDER BY snapshot_type, snapshot_version",
        (decision_id,),
    )


def freeze(
    decision_id: str,
    snapshot_type: str,
    store: Store = STORE,
    retry: bool = False,
    fail_providers: Optional[set] = None,
    as_of: str = "",
    cutoff_at: str = "",
    providers=None,
) -> Optional[Dict[str, Any]]:
    if not flags.decision_context_enabled():
        return None
    existing = latest(decision_id, snapshot_type, store)
    if existing and not retry:
        return existing
    decision = repo.require_decision(decision_id, store)
    stamp, confidence = resolve_cutoff(
        decision, snapshot_type, store, existing=existing, retry=retry,
        override=cutoff_at or as_of,
    )
    run_id = pipeline.start("context_build", [decision_id], {"type": snapshot_type}, store)
    try:
        payload = builder.build(
            decision, stamp, store, providers=providers, fail_providers=fail_providers,
        )
        captured_at = (existing or {}).get("captured_at") or repo.now()
        ctx_inspect.stamp_captured(payload, captured_at)
        if confidence == "unknown" and payload.get("coverage") == "full":
            payload["coverage"] = "partial"
        version = int((existing or {}).get("snapshot_version") or 0) + 1 if existing else 1
        encoded = builder.dumps(payload)
        future_n = int(payload.get("future_rejected_count") or 0)
        temporal_coverage = payload.get("coverage") or "partial"
        if confidence == "unknown" or future_n:
            temporal_coverage = "partial"
        row = {
            "id": _next_id(store),
            "decision_id": decision_id,
            "snapshot_type": snapshot_type,
            "as_of": payload["as_of"],
            "created_at": repo.now(),
            "captured_at": captured_at,
            "context_version": CONTEXT_VERSION,
            "snapshot_version": version,
            "market_regime": payload.get("market_regime") or "",
            "coverage": payload.get("coverage") or "partial",
            "environment": decision.get("environment") or flags.current_environment(),
            "demo": int(decision.get("demo") or (1 if flags.is_demo() else 0)),
            "cutoff_at": stamp,
            "temporal_policy_version": temporal.TEMPORAL_POLICY_VERSION,
            "temporal_coverage": temporal_coverage,
            "temporal_confidence": confidence,
            "future_rejected_count": future_n,
            **encoded,
        }
        repo._insert(store, "decision_context_snapshot", row)
        failed = [k for k, v in (payload.get("provider_status") or {}).items() if v == "failed"]
        pipeline.finish(
            run_id,
            status="partial" if failed else "ok",
            error_code="PROVIDER_FAILED" if failed else "",
            error_message="providers failed: {0}".format(",".join(failed)) if failed else "",
            entity_ids=[decision_id, row["id"]],
            metadata={"coverage": row["coverage"], "failed": failed, "cutoff_at": stamp},
            store=store,
        )
        return row
    except Exception as exc:  # noqa: BLE001
        pipeline.finish(run_id, "failed", "PROVIDER_FAILED", str(exc), [decision_id], store=store)
        return None


def freeze_entry(decision_id: str, store: Store = STORE, **kwargs) -> Optional[Dict[str, Any]]:
    return freeze(decision_id, ENTRY_CONTEXT, store, **kwargs)


def freeze_review(decision_id: str, store: Store = STORE, **kwargs) -> Optional[Dict[str, Any]]:
    return freeze(decision_id, REVIEW_CONTEXT, store, **kwargs)


def diff(decision_id: str, store: Store = STORE) -> Dict[str, Any]:
    entry = latest(decision_id, ENTRY_CONTEXT, store)
    review = latest(decision_id, REVIEW_CONTEXT, store)
    if not entry or not review:
        return {"entry": entry, "review": review, "changes": []}
    changes = []
    e_sent = json.loads(entry.get("sentiment_snapshot_json") or "{}")
    r_sent = json.loads(review.get("sentiment_snapshot_json") or "{}")
    e_stage = ((e_sent.get("mkt_stage") or {}).get("value"))
    r_stage = ((r_sent.get("mkt_stage") or {}).get("value"))
    if e_stage != r_stage:
        changes.append({"field": "market_stage", "entry": e_stage, "review": r_stage})
    e_sec = json.loads(entry.get("sector_snapshot_json") or "{}")
    r_sec = json.loads(review.get("sector_snapshot_json") or "{}")
    e_rs = (e_sec.get("sector_vs_csi300_5d") or {}).get("value")
    r_rs = (r_sec.get("sector_vs_csi300_5d") or {}).get("value")
    if e_rs != r_rs:
        changes.append({"field": "sector_vs_csi300_5d", "entry": e_rs, "review": r_rs})
    return {
        "entry": _public(entry),
        "review": _public(review),
        "changes": changes,
        "note": "环境变化事实。不自动生成 attribution。",
    }


def _public(row: Dict[str, Any]) -> Dict[str, Any]:
    policy = str(row.get("temporal_policy_version") or "")
    return {
        "id": row.get("id"),
        "snapshot_type": row.get("snapshot_type"),
        "as_of": row.get("as_of"),
        "cutoff_at": row.get("cutoff_at") or "",
        "captured_at": row.get("captured_at"),
        "created_at": row.get("created_at"),
        "context_version": row.get("context_version"),
        "temporal_policy_version": policy,
        "temporal_verified": bool(policy),
        "temporal_label": policy or "TEMPORAL_UNVERIFIED",
        "temporal_coverage": row.get("temporal_coverage") or "",
        "temporal_confidence": row.get("temporal_confidence") or "",
        "future_rejected_count": int(row.get("future_rejected_count") or 0),
        "snapshot_version": row.get("snapshot_version"),
        "market_regime": row.get("market_regime"),
        "coverage": row.get("coverage"),
        "index": json.loads(row.get("index_snapshot_json") or "{}"),
        "sector": json.loads(row.get("sector_snapshot_json") or "{}"),
        "sentiment": json.loads(row.get("sentiment_snapshot_json") or "{}"),
        "breadth": json.loads(row.get("breadth_snapshot_json") or "{}"),
        "flow": json.loads(row.get("flow_snapshot_json") or "{}"),
        "overseas": json.loads(row.get("overseas_snapshot_json") or "{}"),
        "freshness": json.loads(row.get("data_freshness_json") or "{}"),
        "data_coverage": json.loads(row.get("data_coverage_json") or "{}"),
        "provider_status": json.loads(row.get("provider_status_json") or "{}"),
        "source_refs": json.loads(row.get("source_refs_json") or "[]"),
    }


def card(decision_id: str, snapshot_type: str = ENTRY_CONTEXT, store: Store = STORE) -> Dict[str, Any]:
    row = latest(decision_id, snapshot_type, store)
    if not row:
        return {"missing": True, "snapshot_type": snapshot_type}
    pub = _public(row)
    idx = pub.get("index") or {}
    indices = idx.get("indices") or idx
    chinext = ((indices.get("chinext") or {}).get("ret_5d") or {})
    failures = [k for k, v in (pub.get("provider_status") or {}).items() if v == "failed"]
    warning = ""
    if failures:
        warning = "Context 中 {0} provider 失败，其它数据已正常冻结。".format("、".join(failures))
    if not pub.get("temporal_verified"):
        extra = "历史快照未经时间完整性校验（TEMPORAL_UNVERIFIED）。"
        warning = "{0} {1}".format(warning, extra).strip()
    return {
        **pub,
        "warning": warning,
        "headline": {
            "market_stage": pub.get("market_regime") or ((pub.get("sentiment") or {}).get("mkt_stage") or {}).get("value"),
            "chinext_5d": chinext.get("value"),
            "sector_rs": ((pub.get("sector") or {}).get("sector_vs_csi300_5d") or {}).get("value"),
            "bank_b": ((pub.get("sentiment") or {}).get("bank_b_level") or {}).get("value")
            or ((pub.get("sector") or {}).get("bank_b_level") or {}).get("value"),
            "vix": ((pub.get("overseas") or {}).get("vix") or {}).get("value"),
            "sox_5d": ((pub.get("overseas") or {}).get("sox_5d_return") or {}).get("value"),
            "coverage": pub.get("coverage"),
            "as_of": pub.get("as_of"),
            "cutoff_at": pub.get("cutoff_at"),
            "temporal_policy": pub.get("temporal_label"),
            "temporal_coverage": pub.get("temporal_coverage") or pub.get("coverage"),
            "future_rejected_count": pub.get("future_rejected_count"),
            "captured_at": pub.get("captured_at"),
        },
    }


def debug(decision_id: str, snapshot_type: str = ENTRY_CONTEXT, store: Store = STORE) -> Dict[str, Any]:
    row = latest(decision_id, snapshot_type, store)
    if not row:
        return {"missing": True, "snapshot_type": snapshot_type, "rows": []}
    pub = _public(row)
    payload = {
        "cutoff_at": pub.get("cutoff_at"),
        "index_snapshot": pub.get("index"),
        "sector_snapshot": pub.get("sector"),
        "sentiment_snapshot": pub.get("sentiment"),
        "breadth_snapshot": pub.get("breadth"),
        "flow_snapshot": pub.get("flow"),
        "overseas_snapshot": pub.get("overseas"),
    }
    rows = ctx_inspect.debug_rows(payload, str(pub.get("cutoff_at") or ""))
    leaks = [r for r in rows if r.get("included") and r.get("reason", "").startswith("LEAK")]
    return {
        "decision_id": decision_id,
        "snapshot_type": snapshot_type,
        "cutoff_at": pub.get("cutoff_at"),
        "temporal_policy_version": pub.get("temporal_policy_version"),
        "temporal_label": pub.get("temporal_label"),
        "coverage": pub.get("coverage"),
        "future_rejected_count": pub.get("future_rejected_count"),
        "rows": rows,
        "leaks": leaks,
    }
