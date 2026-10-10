"""研究评测的硬门槛。放进一条假事实，整次评测失败。"""
from __future__ import annotations

HARD_GATES = (
    "fabricated_source",
    "unsupported_critical_fact",
    "wrong_evidence_link",
    "temporal_leak",
    "fact_inference_confusion",
    "direct_exposure_overclaim",
)


def empty_gates() -> dict:
    return {name: 0 for name in HARD_GATES}


def failed(gates: dict) -> bool:
    return any(gates.get(name, 0) > 0 for name in HARD_GATES)
