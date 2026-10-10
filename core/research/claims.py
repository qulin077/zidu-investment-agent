"""Claim 状态只由证据条数决定，不接受模型自己盖章。"""
from __future__ import annotations

from typing import Dict, Iterable, List


def derive_status(evidence: Iterable[dict]) -> str:
    rows = list(evidence)
    contradicts = [row for row in rows if row.get("support_type") == "CONTRADICT"]
    supports = [row for row in rows if row.get("support_type") == "SUPPORT"]
    if contradicts:
        return "CONTESTED"
    independent = set()
    for row in supports:
        family = row.get("origin_family") or row.get("source_id") or row.get("source_local_id")
        if family:
            independent.add(family)
    if len(independent) >= 2:
        return "CORROBORATED"
    if len(independent) == 1:
        return "SINGLE_SOURCE"
    return "REJECTED"


def evidence_for(claim_local_id: str, evidence: Iterable[dict]) -> List[dict]:
    return [row for row in evidence if row.get("claim_local_id") == claim_local_id]


def index_by_local(claims: Iterable[dict]) -> Dict[str, dict]:
    return {row.get("local_id") or "": row for row in claims if row.get("local_id")}
