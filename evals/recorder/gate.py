"""Recorder Eval Gate。可以漏，不可以编。"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def evaluate_gate(summary: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if int(summary.get("critical_hallucination_count") or 0) > 0:
        reasons.append("Critical Hallucination Count = {0}".format(summary["critical_hallucination_count"]))
    rate = summary.get("unsupported_field_rate")
    if rate is not None and float(rate) > 2.0:
        reasons.append("Unsupported Field Rate = {0}% > 2%".format(rate))
    if int(summary.get("negation_error_count") or 0) > 0:
        reasons.append("Negation Critical Error = {0}".format(summary["negation_error_count"]))
    if int(summary.get("wrong_symbol_critical_count") or 0) > 0:
        reasons.append("Wrong Symbol Critical Error = {0}".format(summary["wrong_symbol_critical_count"]))
    if int(summary.get("wrong_number_critical_count") or 0) > 0:
        reasons.append("Wrong Number Critical Error = {0}".format(summary["wrong_number_critical_count"]))
    return (not reasons), reasons


def can_promote_remote(summary: Dict[str, Any]) -> bool:
    ok, _ = evaluate_gate(summary)
    return ok
