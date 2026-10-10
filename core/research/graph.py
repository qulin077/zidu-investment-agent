"""Claim 之间的轻量关系。不是图数据库。"""
from __future__ import annotations

from core.research.types import CLAIM_RELATIONS


def edge(relation: str, source_claim: str, target_claim: str) -> dict:
    if relation not in CLAIM_RELATIONS:
        raise ValueError("CLAIM_RELATION")
    return {
        "relation": relation,
        "source_claim": source_claim,
        "target_claim": target_claim,
    }


def thesis_refs_known(refs: list, claim_ids: set) -> list:
    return [item for item in refs if item not in claim_ids]
