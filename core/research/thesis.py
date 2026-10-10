"""Thesis 版本差。只比较引用和冲突数量，不改旧行。"""
from __future__ import annotations


def classify_diff(before_refs, after_refs, before_conflicts: int, after_conflicts: int, invalidated: bool = False):
    before = set(before_refs or [])
    after = set(after_refs or [])
    added = sorted(after - before)
    removed = sorted(before - after)
    if invalidated:
        verdict = "INVALIDATED"
    elif removed or after_conflicts > before_conflicts:
        verdict = "WEAKENED"
    elif added:
        verdict = "STRENGTHENED"
    else:
        verdict = "UNCHANGED"
    return verdict, {
        "claim_ids_added": added,
        "claim_ids_removed": removed,
        "conflicts_before": before_conflicts,
        "conflicts_after": after_conflicts,
    }
