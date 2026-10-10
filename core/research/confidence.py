"""正式置信度由规则算。模型可以建议，不能盖章。"""
from __future__ import annotations


def official(evidence: list, contradicted: bool = False) -> str:
    if contradicted:
        return "LOW"
    families = set()
    primary = False
    for row in evidence:
        if row.get("support_type") == "CONTRADICT":
            return "LOW"
        family = row.get("origin_family") or row.get("source_id") or ""
        if family:
            families.add(family)
        if (row.get("source_quality") or "") == "PRIMARY" or row.get("primary"):
            primary = True
    if primary or len(families) >= 2:
        return "HIGH"
    if len(families) == 1 and (evidence and (evidence[0].get("source_quality") or "") == "SECONDARY"):
        return "MEDIUM"
    if families:
        return "LOW"
    return "LOW"
