"""Thesis 里的关键数字必须能回到 Claim 或 Evidence。"""
from __future__ import annotations

import re
from typing import Iterable, List

_DIGITS = re.compile(r"\d+(?:\.\d+)?")


def stray_numbers(thesis: dict, claims: Iterable[dict], evidence: Iterable[dict] | None = None) -> List[str]:
    packet = "\n".join(
        "{0} {1}".format(row.get("claim_text") or "", row.get("evidence_text") or "")
        for row in list(claims) + list(evidence or [])
    )
    blob = " ".join(
        str(thesis.get(key) or "")
        for key in ("summary", "invalidation", "catalysts", "risks", "open_questions", "company_exposure")
    )
    blob = re.sub(r"C\d+", " ", blob)
    return [num for num in _DIGITS.findall(blob) if num not in packet]
