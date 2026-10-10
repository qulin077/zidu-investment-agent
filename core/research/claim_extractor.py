"""从已读到的正文里收 Claim。引文必须是正文的子串。"""
from __future__ import annotations

from typing import Iterable, List, Optional


def review(draft: dict) -> List[dict]:
    """返回不能进入正式 Claim 的原因。通过则空列表。"""
    sources = {row.get("local_id"): (row.get("body") or row.get("content") or "") for row in draft.get("sources") or []}
    evidence = list(draft.get("evidence") or [])
    by_claim = {}
    errors = []
    for item in evidence:
        by_claim.setdefault(item.get("claim_local_id"), []).append(item)
        span = item.get("evidence_text") or ""
        body = sources.get(item.get("source_local_id"))
        if body is None:
            continue
        if span and span not in body:
            errors.append({
                "code": "GROUNDING_FAILED",
                "message": "引文不是来源正文的子串。",
            })
    for claim in draft.get("claims") or []:
        kind = claim.get("claim_type") or ""
        linked = by_claim.get(claim.get("local_id")) or []
        if kind == "INFERENCE" and not (claim.get("premise_claim_ids") or []):
            errors.append({"code": "INFERENCE_INVALID", "message": "推断没有 premise_claim_ids。"})
        if kind == "FACT" and claim.get("critical") and not linked:
            errors.append({"code": "WRITE_BLOCKED", "message": "关键事实没有证据。"})
        if kind == "FACT" and not linked:
            errors.append({"code": "GROUNDING_FAILED", "message": "事实没有可核对的引文。"})
    return errors


def grounded(evidence_text: str, bodies: Iterable[str]) -> bool:
    text = evidence_text or ""
    if not text:
        return False
    return any(text in (body or "") for body in bodies)
