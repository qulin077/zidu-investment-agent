"""给固定来源上的远程输出打分。不写正式 Thesis。"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List

from core.research.types import FORBIDDEN_PHRASES

_DIGITS = re.compile(r"\d+(?:\.\d+)?")
_FORECAST = ("预计", "预测", "多头", "空头", "目标价")


def score_extraction(claims: Iterable[dict], sources: Dict[str, str]) -> dict:
    rows = []
    for claim in claims:
        source_id = claim.get("source_id") or claim.get("source_local_id") or ""
        span = (claim.get("evidence_text") or "").strip()
        body = sources.get(source_id, "")
        in_cited = bool(span) and span in body
        in_other = [key for key, text in sources.items() if key != source_id and span and span in text]
        kind = claim.get("claim_type") or ""
        forecast_as_fact = kind == "FACT" and any(token in (claim.get("claim_text") or "") or token in span for token in _FORECAST)
        grounded = in_cited and not forecast_as_fact
        rows.append({
            "claim_text": claim.get("claim_text") or "",
            "claim_type": kind,
            "source_id": source_id,
            "evidence_text": span,
            "grounded": grounded,
            "wrong_link": bool(span) and not in_cited,
            "span_in_other_source": bool(in_other),
            "forecast_as_fact": forecast_as_fact,
            "critical": bool(claim.get("critical")),
        })
    emitted = len(rows)
    grounded_n = sum(1 for row in rows if row["grounded"])
    return {
        "emitted": emitted,
        "grounded": grounded_n,
        "ungrounded": emitted - grounded_n,
        "wrong_link": sum(1 for row in rows if row["wrong_link"]),
        "forecast_as_fact": sum(1 for row in rows if row["forecast_as_fact"]),
        "buy_language": _forbidden(claims),
        "rows": rows,
    }


def grounded_claims(claims: Iterable[dict], sources: Dict[str, str]) -> List[dict]:
    scored = score_extraction(claims, sources)
    kept = []
    for claim, row in zip(claims, scored["rows"]):
        if not row["grounded"]:
            continue
        item = dict(claim)
        item["claim_type"] = row["claim_type"]
        item["evidence_text"] = row["evidence_text"]
        item["source_id"] = row["source_id"]
        kept.append(item)
    return kept


def score_thesis(thesis: dict, claims: Iterable[dict]) -> dict:
    packet = "\n".join(
        "{0} {1}".format(row.get("claim_text") or "", row.get("evidence_text") or "")
        for row in claims
    )
    known = {row.get("local_id") or row.get("id") or "" for row in claims}
    known.discard("")
    blob = " ".join(
        str(thesis.get(key) or "")
        for key in ("summary", "invalidation", "catalysts", "risks", "open_questions", "company_exposure")
    )
    blob = re.sub(r"C\d+", " ", blob)
    refs = list(thesis.get("evidence_refs") or [])
    missing_refs = [item for item in refs if item not in known]
    stray_numbers = [num for num in _DIGITS.findall(blob) if num not in packet]
    exposures = thesis.get("company_exposure") or []
    direct = [
        row.get("company") or ""
        for row in exposures
        if isinstance(row, dict) and (row.get("exposure_type") or "") == "DIRECT"
    ]
    return {
        "buy_language": any(phrase in blob for phrase in FORBIDDEN_PHRASES),
        "missing_refs": missing_refs,
        "stray_numbers": stray_numbers,
        "direct_without_gate": direct,
        "has_summary": bool((thesis.get("summary") or "").strip()),
        "open_questions": list(thesis.get("open_questions") or []),
    }


def _forbidden(claims: Iterable[dict]) -> bool:
    blob = " ".join((row.get("claim_text") or "") for row in claims)
    return any(phrase in blob for phrase in FORBIDDEN_PHRASES)
