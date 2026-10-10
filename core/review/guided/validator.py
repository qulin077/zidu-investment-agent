"""Guided Review 输出校验。越权 / 猜情绪 / 用盈亏打分 / 编证据 → 拒绝。"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from core.review.guided.types import ERROR_TYPES

RECOMMEND = ("明天应该买", "建议换成", "建议卖出当前", "建议买", "最该买", "推荐")
PNL_QUALITY = ("好决策", "优秀交易员", "A+", "85分", "打分", "优秀交易")
EMOTION_GUESS = ("FOMO", "情绪错误", "害怕踏空所以", "明显是情绪")


class GuidedValidationError(ValueError):
    pass


def _blob(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def validate(payload: Dict[str, Any], facts: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    if payload.get("agent_conclusion") not in (None, "", {}, []):
        issues.append("agent_conclusion 必须为 null 直到用户确认")
    if payload.get("primary_error"):
        issues.append("不能自动落 primary_error")
    if payload.get("write_attribution") or payload.get("auto_attribution"):
        issues.append("violation 不能静默映射 attribution")

    text = _blob(payload)
    for needle in RECOMMEND:
        if needle in text:
            issues.append("Unsupported Critical Claim: 不生成股票推荐（{0}）".format(needle))
    for needle in PNL_QUALITY:
        if needle in text:
            issues.append("PnL Bias Error: 禁止用收益当质量标签（{0}）".format(needle))

    question = str(payload.get("question") or "")
    extra_qs = payload.get("questions") or payload.get("extra_questions")
    if extra_qs:
        issues.append("一次只能问一个核心问题")
    if question.count("？") > 2 and "\n" in question:
        issues.append("一次只能问一个核心问题")

    known = {item.get("id") for item in (facts.get("evidence") or [])}
    for stmt in payload.get("fact_summary") or []:
        ref = (stmt or {}).get("evidence_ref") or ""
        if ref and known and ref not in known:
            issues.append("Unsupported Critical Claim: 未知 evidence_ref {0}".format(ref))

    emotion_ok = bool(facts.get("emotion_self_report") or facts.get("user_confirmed_emotion"))
    for cand in payload.get("attribution_candidates") or []:
        kind = cand.get("type") or ""
        if kind and kind not in ERROR_TYPES:
            issues.append("未知 attribution type：{0}".format(kind))
        refs = cand.get("evidence_refs") or []
        if not refs:
            issues.append("Unsupported Critical Claim: candidate 缺 evidence")
        if kind == "EMOTION_ERROR" and not emotion_ok:
            issues.append("Emotion Inference Violation")
        for ref in refs:
            if known and ref not in known:
                issues.append("Unsupported Critical Claim: candidate 引用了不存在的证据 {0}".format(ref))

    if "EMOTION_ERROR" in text and not emotion_ok:
        if any(n in text for n in EMOTION_GUESS) or '"type": "EMOTION_ERROR"' in text or "EMOTION_ERROR" in text:
            if not any("Emotion Inference" in i for i in issues):
                # 仅当作为结论/候选出现
                if any((c or {}).get("type") == "EMOTION_ERROR" for c in (payload.get("attribution_candidates") or [])):
                    issues.append("Emotion Inference Violation")

    codes = set(facts.get("violation_codes") or [])
    if "SIZE_EXCEEDED" in codes and "你有没有超仓" in question:
        issues.append("Question Relevance: 超仓已是事实，不应再问是否超仓")

    if facts.get("process_followed") and facts.get("pnl_sign") == "loss":
        if any(k in text for k in ("因为亏损", "亏损所以是 ERROR", "所以是错误")):
            issues.append("PnL Bias Error: Good Loss 不得因亏损判错")

    if facts.get("quote_coverage") and facts.get("quote_coverage") != "full":
        if "完整 MFE" in text or "完整回撤" in text:
            issues.append("partial coverage 不过度解释")

    if payload.get("needs_user_input") is False and payload.get("unresolved_dimension") == "ATTRIBUTION":
        issues.append("Attribution 必须向用户确认")

    return issues


def assert_valid(payload: Dict[str, Any], facts: Dict[str, Any]) -> Dict[str, Any]:
    issues = validate(payload, facts)
    hard = [i for i in issues if any(k in i for k in (
        "Unsupported Critical Claim", "Emotion Inference", "静默映射", "primary_error",
        "股票推荐",
    ))]
    if hard:
        raise GuidedValidationError("；".join(hard))
    return payload
