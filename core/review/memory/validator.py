"""Rule / Pattern 文本门。拒绝不可执行规则、人格标签、无证据规则。"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from core.review.memory.types import ACTIONABLE_MARKERS, PERSONA_BANNED, VAGUE_RULES


class MemoryError(Exception):
    pass


def personality_hits(text: str) -> List[str]:
    blob = text or ""
    return [p for p in PERSONA_BANNED if p in blob]


def validate_summary(summary: str, trigger: str = "", behavior: str = "") -> List[str]:
    issues: List[str] = []
    blob = " ".join([summary or "", trigger or "", behavior or ""])
    hits = personality_hits(blob)
    if hits:
        issues.append("人格化标签：" + "、".join(hits))
    return issues


def validate_rule(
    rule_text: str,
    trigger: str = "",
    expected_behavior: str = "",
    evidence_decision_ids: Sequence[str] = (),
) -> List[str]:
    issues: List[str] = []
    text = (rule_text or "").strip()
    trig = (trigger or "").strip()
    expected = (expected_behavior or "").strip()
    if not [d for d in evidence_decision_ids if d]:
        issues.append("Unsupported Rule：没有 evidence decisions")
    if not text:
        issues.append("Rule 文本为空")
        return issues
    hits = personality_hits(text + trig + expected)
    if hits:
        issues.append("人格化标签：" + "、".join(hits))
    vague = [v for v in VAGUE_RULES if v in text]
    has_structure = bool(trig and expected)
    has_markers = any(m in text for m in ACTIONABLE_MARKERS)
    if vague and not has_structure and not has_markers:
        issues.append("vague rule：{0}".format("、".join(vague)))
    if not has_structure and not has_markers:
        issues.append("Rule 不可执行：缺少 trigger / expected behavior")
    return issues


def assert_rule_ok(rule_text: str, trigger: str, expected: str, evidence: Sequence[str]) -> None:
    issues = validate_rule(rule_text, trigger, expected, evidence)
    if issues:
        raise MemoryError("；".join(issues))


def assert_no_persona(payload: Dict[str, Any]) -> None:
    blob = " ".join(str(payload.get(k) or "") for k in ("summary", "common_trigger", "common_behavior", "rule_text"))
    hits = personality_hits(blob)
    if hits:
        raise MemoryError("人格化标签：" + "、".join(hits))
