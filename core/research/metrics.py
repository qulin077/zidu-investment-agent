"""研究质量只看证据覆盖和冲突，不看推荐收益。"""
from __future__ import annotations

from typing import Optional

from core.store import STORE, Store


def _rate(num: int, den: int) -> Optional[float]:
    if den <= 0:
        return None
    return round(num / float(den), 4)


def product_metrics(store: Store = STORE) -> dict:
    try:
        runs = store.query("SELECT status, llm_calls, tokens, cost, project_id FROM research_run")
        claims = store.query("SELECT id, claim_type, status, critical FROM research_claim")
        evidence = store.query("SELECT claim_id FROM research_evidence")
        conflicts = store.query("SELECT status FROM research_conflict")
        theses = store.query("SELECT project_id, version FROM research_thesis")
    except Exception:  # noqa: BLE001
        return {}
    covered_ids = {row["claim_id"] for row in evidence}
    critical = [row for row in claims if int(row.get("critical") or 0)]
    critical_covered = [row for row in critical if row["id"] in covered_ids]
    succeeded = [row for row in runs if row.get("status") == "succeeded"]
    resolved = [row for row in conflicts if row.get("status") == "RESOLVED"]
    corroborated = [row for row in claims if row.get("status") == "CORROBORATED"]
    unsupported = [
        row for row in claims
        if row.get("claim_type") == "FACT" and row["id"] not in covered_ids
    ]
    projects = {row.get("project_id") for row in theses if row.get("project_id")}
    updates = len(theses) - len(projects)
    token_vals = [row.get("tokens") for row in runs if row.get("tokens") is not None]
    cost_vals = [row.get("cost") for row in runs if row.get("cost") is not None]
    return {
        "research_completion_rate": _rate(len(succeeded), len(runs)),
        "evidence_coverage": _rate(len(covered_ids), len(claims)),
        "critical_claim_evidence_coverage": _rate(len(critical_covered), len(critical)),
        "corroborated_claim_rate": _rate(len(corroborated), len(claims)),
        "conflict_resolution_rate": _rate(len(resolved), len(conflicts)),
        "unsupported_claim_rate": _rate(len(unsupported), len(claims)),
        "thesis_update_frequency": _rate(updates, len(projects)) if projects else None,
        "llm_calls_per_project": _rate(sum(int(row.get("llm_calls") or 0) for row in runs), len(projects)) if projects else None,
        "tokens_per_project": _rate(sum(token_vals), len(projects)) if token_vals and projects else None,
        "cost_per_project": _rate(int(sum(cost_vals)), len(projects)) if cost_vals and projects else None,
    }
