"""研究引用复用 P2.05 的时间比较。available_at 晚于 thesis as_of 的来源不能进入该版。"""
from __future__ import annotations

import json
from typing import Optional

from core.context.temporal import parse_dt
from core.store import STORE, Store


def available(available_at: str, as_of: str) -> bool:
    left = parse_dt(available_at or "")
    right = parse_dt(as_of or "")
    if left is None or right is None:
        return False
    return left <= right


def future_source_ids(sources: list, evidence: list, as_of: str) -> set:
    by_local = {row.get("local_id"): row for row in sources}
    by_id = {row.get("id"): row for row in sources}
    late = set()
    for item in evidence:
        source = by_local.get(item.get("source_local_id")) or by_id.get(item.get("source_id"))
        if source is None:
            continue
        if not available(source.get("available_at") or "", as_of):
            late.add(source.get("local_id") or source.get("id"))
    return late


def leak_rows(store: Store = STORE) -> list:
    """已入库的 Thesis 若引用了更晚才可见的来源，记为泄漏。"""
    leaks = []
    theses = store.query("SELECT id, version, as_of, evidence_refs_json FROM research_thesis")
    for thesis in theses:
        refs = json.loads(thesis.get("evidence_refs_json") or "[]")
        if not refs:
            continue
        marks = ",".join("?" for _ in refs)
        claims = store.query(
            "SELECT id FROM research_claim WHERE id IN ({0})".format(marks),
            tuple(refs),
        )
        claim_ids = [row["id"] for row in claims]
        if not claim_ids:
            continue
        marks = ",".join("?" for _ in claim_ids)
        evidence = store.query(
            "SELECT source_id FROM research_evidence WHERE claim_id IN ({0})".format(marks),
            tuple(claim_ids),
        )
        for item in evidence:
            source = store.query(
                "SELECT id, available_at, title FROM research_source WHERE id = ?",
                (item["source_id"],),
            )
            if not source:
                continue
            if not available(source[0].get("available_at") or "", thesis.get("as_of") or ""):
                leaks.append({
                    "thesis_id": thesis["id"],
                    "version": thesis["version"],
                    "source_id": source[0]["id"],
                    "available_at": source[0].get("available_at") or "",
                    "as_of": thesis.get("as_of") or "",
                })
    return leaks


def audit(store: Store = STORE) -> dict:
    rows = leak_rows(store)
    return {
        "status": "FAIL" if rows else "PASS",
        "temporal_leak": len(rows),
        "rows": rows,
    }
